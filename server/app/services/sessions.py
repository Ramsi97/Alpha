"""Session lifecycle and the finish-validation transaction (plan section 8).

finish_session() is the core of the whole backend: every rule in plan
section 8.3 is checked here, in order, inside one transaction with the
session row locked (SELECT ... FOR UPDATE), so two concurrent finish calls
for the same session can't both award XP.
"""

import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.core.redis import get_redis
from app.models.game import Game
from app.models.score import Score
from app.models.session import GameSession
from app.models.user import User
from app.models.xp_event import XpEvent
from app.services import leaderboard
from app.services.achievements import check_achievements
from app.services.challenges import check_and_record_beats
from app.services.notifications import queue_notification
from app.services.referrals import activate_referral_if_eligible
from app.services.seasons import active_season_id
from app.services.settings_store import get_setting
from app.services.tournaments import record_tournament_score
from app.services.xp import DEFAULT_DAILY_GAME_XP_CAP, DEFAULT_RUN_THRESHOLDS, compute_run_xp, level_for_xp, level_progress

SESSION_MAX_AGE = timedelta(hours=2)


def _hash_token(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()


MIN_SAMPLE_FOR_PERCENTILE_CHECK = 20
OUTLIER_MULTIPLIER = 2.0  # plan section 17: "far above" the 99th percentile, not just above it


async def _is_statistical_outlier(db: AsyncSession, game_id: int, variant: str | None, score: int) -> bool:
    """Plan section 17: "scores far above the 99th percentile for a
    game/variant are held for review" — a second, independent flagging
    signal alongside the time-based max_score_per_second check. Needs a
    real distribution to compare against, so it's a no-op until there's a
    reasonable sample of past legitimate (non-flagged) runs."""
    sample_count = (
        await db.execute(
            select(func.count()).select_from(Score).where(
                Score.game_id == game_id, Score.variant == variant, Score.flagged == False  # noqa: E712
            )
        )
    ).scalar_one()
    if sample_count < MIN_SAMPLE_FOR_PERCENTILE_CHECK:
        return False

    p99 = (
        await db.execute(
            select(func.percentile_cont(0.99).within_group(Score.value)).where(
                Score.game_id == game_id, Score.variant == variant, Score.flagged == False  # noqa: E712
            )
        )
    ).scalar_one()
    return p99 is not None and p99 > 0 and score > p99 * OUTLIER_MULTIPLIER


def _daily_seed(slug: str, variant: str | None) -> str:
    # Deterministic per UTC day + game + variant (plan section 8.2), never
    # the player's device clock. Safe to compute for every game, not just
    # ones that currently use it for daily-puzzle determinism — it's inert
    # for games that just treat it as a regular seed.
    today = datetime.now(UTC).date().isoformat()
    digest = hashlib.sha256(f"{today}:{slug}:{variant or ''}".encode()).hexdigest()
    return str(int(digest[:12], 16))


async def create_session(db: AsyncSession, user: User, game: Game, variant: str | None) -> tuple[GameSession, str]:
    if game.status != "active":
        raise ApiError(404, "not_found", f"No active game with slug '{game.slug}'.")
    if game.variants and variant not in game.variants:
        raise ApiError(400, "invalid_variant", f"'{variant}' is not a valid variant for '{game.slug}'.")
    if not game.variants and variant is not None:
        raise ApiError(400, "invalid_variant", f"'{game.slug}' does not support variants.")

    # One active run per user per game (plan section 8.2).
    await db.execute(
        GameSession.__table__.update()
        .where(GameSession.user_id == user.id, GameSession.game_id == game.id, GameSession.status == "active")
        .values(status="expired")
    )

    token = secrets.token_urlsafe(32)
    session = GameSession(
        id=uuid.uuid4(),
        user_id=user.id,
        game_id=game.id,
        variant=variant,
        token_hash=_hash_token(token),
        seed=_daily_seed(game.slug, variant),
        status="active",
    )
    db.add(session)
    await db.flush()
    return session, token


async def _reconstruct_finish_response(db: AsyncSession, session: GameSession, user: User) -> dict:
    """Idempotent replay: the session is already finished, so recompute the
    response from what's already stored rather than reprocessing (plan
    section 8.3 point 8 — a repeated request cannot double-reward)."""
    score_row = (await db.execute(select(Score).where(Score.session_id == session.id))).scalar_one_or_none()
    redis = get_redis()
    key = leaderboard.game_leaderboard_key(session.game_id, session.variant)
    best = (
        await db.execute(
            select(func.max(Score.value)).where(
                Score.user_id == user.id, Score.game_id == session.game_id,
                Score.variant == session.variant, Score.flagged == False,  # noqa: E712
            )
        )
    ).scalar_one()
    return {
        "score": score_row.value if score_row else 0,
        "xp_awarded": score_row.xp_awarded if score_row else 0,
        "total_xp": user.total_xp,
        "level": user.level,
        "level_progress": level_progress(user.total_xp, user.level),
        "personal_best": best or 0,
        "rank": await leaderboard.get_rank(redis, key, user.id),
        "new_achievements": [],
        "flagged": score_row.flagged if score_row else False,
    }


async def finish_session(
    db: AsyncSession,
    user: User,
    session_id: uuid.UUID,
    token: str,
    score: int,
    variant: str | None,
) -> dict:
    # Lock the session row for the duration of this transaction so two
    # concurrent finish calls serialize instead of racing (plan section 8.3).
    session = (
        await db.execute(select(GameSession).where(GameSession.id == session_id).with_for_update())
    ).scalar_one_or_none()
    if session is None or session.user_id != user.id:
        raise ApiError(404, "not_found", "Session not found.")

    if session.status == "finished":
        return await _reconstruct_finish_response(db, session, user)
    if session.status != "active":
        raise ApiError(409, "session_not_active", f"Session is '{session.status}', not active.")

    if not hmac.compare_digest(_hash_token(token), session.token_hash):
        raise ApiError(401, "invalid_token", "Session token does not match.")

    now = datetime.now(UTC)
    started_at = session.started_at if session.started_at.tzinfo else session.started_at.replace(tzinfo=UTC)
    if now - started_at > SESSION_MAX_AGE:
        session.status = "expired"
        session.finished_at = now
        await db.commit()
        raise ApiError(410, "session_expired", "This session has expired.")

    game = (await db.execute(select(Game).where(Game.id == session.game_id))).scalar_one()

    duration_seconds = max(1, (now - started_at).total_seconds())  # avoid div-by-zero below

    reject_reason: str | None = None
    if duration_seconds < game.min_play_seconds:
        reject_reason = "play time below minimum"
    elif not isinstance(score, int) or score < 0 or score > game.max_score:
        reject_reason = "score out of range"
    elif variant != session.variant:
        reject_reason = "variant does not match session"

    if reject_reason is not None:
        session.status = "rejected"
        session.finished_at = now
        row = Score(
            user_id=user.id, game_id=game.id, session_id=session.id,
            variant=session.variant, value=max(0, min(score, game.max_score)), xp_awarded=0, flagged=False,
        )
        db.add(row)
        await db.commit()
        raise ApiError(422, "rejected", reject_reason)

    flagged = (score / duration_seconds) > float(game.max_score_per_second)
    if not flagged:
        flagged = await _is_statistical_outlier(db, game.id, session.variant, score)

    xp_awarded = 0
    if not flagged:
        today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        todays_awarding_scores = (
            await db.execute(
                select(Score.xp_awarded).where(
                    Score.user_id == user.id,
                    Score.game_id == game.id,
                    Score.created_at >= today_start,
                    Score.xp_awarded > 0,
                )
            )
        ).scalars().all()
        runs_today = len(todays_awarding_scores)
        game_xp_earned_today = sum(todays_awarding_scores)

        thresholds_setting = await get_setting(db, "xp_run_thresholds", list(DEFAULT_RUN_THRESHOLDS))
        thresholds = tuple(tuple(x) for x in thresholds_setting)
        daily_cap = await get_setting(db, "daily_game_xp_cap", DEFAULT_DAILY_GAME_XP_CAP)

        award = compute_run_xp(
            score=score,
            xp_rate=float(game.xp_rate),
            max_xp_per_run=game.max_xp_per_run,
            runs_today=runs_today,
            game_xp_earned_today=game_xp_earned_today,
            daily_game_xp_cap=daily_cap,
            thresholds=thresholds,
        )
        xp_awarded = award.xp

    score_row = Score(
        user_id=user.id, game_id=game.id, session_id=session.id,
        variant=session.variant, value=score, xp_awarded=xp_awarded, flagged=flagged,
    )
    db.add(score_row)

    if xp_awarded > 0:
        xp_event = XpEvent(
            user_id=user.id, source="game", amount=xp_awarded,
            ref_type="game_session", ref_id=str(session.id),
            idempotency_key=f"score:{session.id}",
            season_id=await active_season_id(db),
        )
        db.add(xp_event)
        try:
            await db.flush()
        except IntegrityError as e:
            # idempotency_key collision: this exact session was already
            # processed by a request that raced us past the row lock
            # somehow (shouldn't happen given with_for_update, but the
            # unique constraint is the last line of defense).
            await db.rollback()
            refreshed = (
                await db.execute(select(GameSession).where(GameSession.id == session_id))
            ).scalar_one()
            return await _reconstruct_finish_response(db, refreshed, user)

        previous_level = user.level
        user.total_xp += xp_awarded
        user.level = level_for_xp(user.total_xp)
        if user.level > previous_level:
            queue_notification(db, user.id, "level_up", {"level": user.level})

    session.status = "finished"
    session.finished_at = now

    best = (
        await db.execute(
            select(func.max(Score.value)).where(
                Score.user_id == user.id, Score.game_id == game.id,
                Score.variant == session.variant, Score.flagged == False,  # noqa: E712
            )
        )
    ).scalar_one()

    await db.commit()

    # score_submitted (plan section 11 event table) — checked for every
    # finished run, flagged or not: a flagged run still counts toward
    # total_runs, it just didn't earn XP (score_at_least conditions still
    # correctly exclude flagged scores, see achievements.py).
    newly_unlocked = await check_achievements(db, user)

    if not flagged:
        # Referral activation requires a *valid* run (plan section 12.4) —
        # a flagged score shouldn't be able to trigger it.
        activated = await activate_referral_if_eligible(db, user)
        if activated is not None:
            await db.commit()

        # Same reasoning for challenge beats (plan section 12.5) — an
        # implausible score shouldn't be able to "beat" a friend's challenge.
        await check_and_record_beats(db, user, game.id, session.variant, score)

        # Same reasoning for tournament entries (plan section 13).
        await record_tournament_score(db, user.id, game.id, session.variant, score)

    redis = get_redis()
    rank = None
    if not flagged:
        await leaderboard.record_game_score(redis, user.id, game.id, session.variant, score)
        await leaderboard.record_total_xp(redis, user.id, user.total_xp)
        key = leaderboard.game_leaderboard_key(game.id, session.variant)
        rank = await leaderboard.get_rank(redis, key, user.id)

    return {
        "score": score,
        "xp_awarded": xp_awarded,
        "total_xp": user.total_xp,
        "level": user.level,
        "level_progress": level_progress(user.total_xp, user.level),
        "personal_best": best or 0,
        "rank": rank,
        "new_achievements": [a.key for a in newly_unlocked],
        "flagged": flagged,
    }
