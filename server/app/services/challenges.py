"""Friend duels (plan section 12.5).

A challenge can be beaten by more than one friend (share it widely) — the
unique (challenge_id, beater_id) constraint on ChallengeBeat just stops any
single beater re-triggering the challenger's reward on a repeat run, not
the challenge itself from being beaten multiple times by different people.
"""

import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.challenge import Challenge, ChallengeBeat
from app.models.user import User
from app.models.xp_event import XpEvent
from app.services.notifications import queue_notification
from app.services.seasons import active_season_id
from app.services.settings_store import get_setting
from app.services.xp import level_for_xp

DEFAULT_CHALLENGE_BEAT_XP = 15
DEFAULT_CHALLENGE_TTL_DAYS = 7


async def create_challenge(
    db: AsyncSession, challenger: User, game_id: int, variant: str | None, score_to_beat: int
) -> Challenge:
    ttl_days = await get_setting(db, "challenge_ttl_days", DEFAULT_CHALLENGE_TTL_DAYS)
    challenge = Challenge(
        challenger_id=challenger.id, game_id=game_id, variant=variant, score_to_beat=score_to_beat,
        token=secrets.token_urlsafe(8),
        expires_at=datetime.now(UTC) + timedelta(days=ttl_days),
    )
    db.add(challenge)
    await db.flush()
    return challenge


async def get_active_challenge_by_token(db: AsyncSession, token: str) -> Challenge | None:
    challenge = (await db.execute(select(Challenge).where(Challenge.token == token))).scalar_one_or_none()
    if challenge is None:
        return None
    expires_at = challenge.expires_at if challenge.expires_at.tzinfo else challenge.expires_at.replace(tzinfo=UTC)
    if expires_at < datetime.now(UTC):
        return None
    return challenge


async def check_and_record_beats(
    db: AsyncSession, user: User, game_id: int, variant: str | None, score: int
) -> list[Challenge]:
    """Call after a successful, non-flagged finish. Finds every active
    challenge this run just beat (same game+variant, someone else's
    challenge, score_to_beat cleared) that this user hasn't already
    triggered a reward for, and rewards the challenger once per beater."""
    now = datetime.now(UTC)
    candidates = (
        await db.execute(
            select(Challenge).where(
                Challenge.game_id == game_id, Challenge.variant == variant,
                Challenge.score_to_beat <= score, Challenge.expires_at >= now,
                Challenge.challenger_id != user.id,
            )
        )
    ).scalars().all()
    if not candidates:
        return []

    # Check for existing beats up front rather than insert-and-catch: a
    # rollback() after a mid-loop IntegrityError would expire every object
    # in the session, including `user` — which the caller (finish_session)
    # keeps using afterward. Async SQLAlchemy can't transparently re-fetch
    # an expired attribute on plain sync access (no await), so that would
    # crash with MissingGreenlet the next time anything touches `user`.
    already_beaten_ids = set(
        (
            await db.execute(
                select(ChallengeBeat.challenge_id).where(
                    ChallengeBeat.challenge_id.in_([c.id for c in candidates]), ChallengeBeat.beater_id == user.id
                )
            )
        ).scalars().all()
    )

    beat_xp = await get_setting(db, "challenge_beat_xp", DEFAULT_CHALLENGE_BEAT_XP)
    season_id = await active_season_id(db)
    beaten: list[Challenge] = []

    for challenge in candidates:
        if challenge.id in already_beaten_ids:
            continue
        db.add(ChallengeBeat(challenge_id=challenge.id, beater_id=user.id))
        try:
            await db.flush()
        except IntegrityError:
            # Genuine race: two concurrent finish requests for this same
            # user both passed the already_beaten_ids check above before
            # either committed. rollback() expires every object in the
            # session (including `user`, which the caller keeps using
            # afterward) so refresh it explicitly before moving on, same
            # as do_checkin's duplicate-ledger-row handling.
            await db.rollback()
            await db.refresh(user)
            continue

        challenger = (await db.execute(select(User).where(User.id == challenge.challenger_id))).scalar_one()
        db.add(XpEvent(
            user_id=challenger.id, source="challenge", amount=beat_xp,
            ref_type="challenge_beat", ref_id=f"{challenge.id}:{user.id}",
            idempotency_key=f"challenge_beat:{challenge.id}:{user.id}",
            season_id=season_id,
        ))
        challenger.total_xp += beat_xp
        challenger.level = level_for_xp(challenger.total_xp)
        queue_notification(db, challenger.id, "challenge_beaten", {"beater_id": user.id, "score": score})
        beaten.append(challenge)

    if beaten:
        await db.commit()
    return beaten
