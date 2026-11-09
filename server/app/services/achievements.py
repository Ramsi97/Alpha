"""Achievements (plan section 11).

No separate event-bus class — "fire on score_submitted" and "fire on
checked_in" just means "call check_achievements() after each of those
services commits," which is what app/services/sessions.py and
app/services/checkin.py do. Level-up achievements don't need their own
trigger: by the time either caller runs this, user.level already reflects
whatever XP was just awarded, so a `{"type": "level", ...}` condition is
checked for free on every call. Good enough at this scale (plan section 11:
"simple in-process publish after commit... move to a Redis stream when
needed") — not needed yet.
"""

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.achievement import Achievement, UserAchievement
from app.models.game import Game
from app.models.score import Score
from app.models.user import User
from app.models.xp_event import XpEvent
from app.services.seasons import active_season_id


def check_condition_simple(condition: dict, user: User) -> bool | None:
    """Conditions answerable from the User row alone, no query needed.
    Returns None for condition types that need one (the caller falls
    through to _condition_met for those)."""
    t = condition.get("type")
    if t == "level":
        return user.level >= condition["value"]
    if t == "streak":
        return user.streak_count >= condition["value"]
    return None


async def _condition_met(db: AsyncSession, user: User, condition: dict) -> bool:
    simple = check_condition_simple(condition, user)
    if simple is not None:
        return simple

    t = condition.get("type")
    if t == "total_runs":
        count = (await db.execute(select(func.count()).select_from(Score).where(Score.user_id == user.id))).scalar_one()
        return count >= condition["value"]
    if t == "score_at_least":
        game = (await db.execute(select(Game).where(Game.slug == condition["game"]))).scalar_one_or_none()
        if game is None:
            return False
        best = (
            await db.execute(
                select(func.max(Score.value)).where(
                    Score.user_id == user.id, Score.game_id == game.id, Score.flagged == False  # noqa: E712
                )
            )
        ).scalar_one()
        return (best or 0) >= condition["value"]
    return False


async def check_achievements(db: AsyncSession, user: User) -> list[Achievement]:
    """Unlocks any newly-earned achievements, awards their XP (with an
    idempotency key, same ledger as everything else), and returns the
    list newly unlocked this call. Call after any event that could unlock
    one — currently: after finish_session commits, after do_checkin
    commits. Caller is responsible for already having committed whatever
    triggered this (we read user.level/streak_count fresh off the object)."""
    already_unlocked = set(
        (await db.execute(select(UserAchievement.achievement_id).where(UserAchievement.user_id == user.id)))
        .scalars()
        .all()
    )
    query = select(Achievement)
    if already_unlocked:
        query = query.where(Achievement.id.notin_(already_unlocked))
    candidates = (await db.execute(query)).scalars().all()

    newly_unlocked = []
    season_id_fetched = False
    season_id = None
    for achievement in candidates:
        if await _condition_met(db, user, achievement.condition):
            db.add(UserAchievement(user_id=user.id, achievement_id=achievement.id))
            if achievement.xp_reward:
                if not season_id_fetched:
                    season_id = await active_season_id(db)
                    season_id_fetched = True
                db.add(XpEvent(
                    user_id=user.id, source="achievement", amount=achievement.xp_reward,
                    ref_type="achievement", ref_id=str(achievement.id),
                    idempotency_key=f"achievement:{user.id}:{achievement.id}",
                    season_id=season_id,
                ))
                user.total_xp += achievement.xp_reward
                from app.services.xp import level_for_xp  # local import avoids a cycle with sessions.py
                user.level = level_for_xp(user.total_xp)
            newly_unlocked.append(achievement)

    if not newly_unlocked:
        return []

    try:
        await db.commit()
    except IntegrityError:
        # Lost a race with a concurrent call for the same user (e.g. two
        # requests finishing at once). The idempotency_key/primary-key
        # constraints already prevented a double-award; just don't report
        # anything new from this call — the next check_achievements() call
        # will see them as already unlocked.
        await db.rollback()
        return []

    return newly_unlocked
