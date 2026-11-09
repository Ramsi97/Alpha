"""Daily check-in and streaks (plan section 11).

UTC day for the MVP (plan section 23 — per-user time zones are an explicit
later-phase item, not a bug to fix now).
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime


@dataclass
class StreakUpdate:
    already_checked_in: bool
    new_streak: int
    freezes_used: int


def compute_streak_update(
    last_checkin_date: date | None, today: date, streak_count: int, streak_freezes: int
) -> StreakUpdate:
    if last_checkin_date == today:
        return StreakUpdate(already_checked_in=True, new_streak=streak_count, freezes_used=0)
    if last_checkin_date is None:
        return StreakUpdate(already_checked_in=False, new_streak=1, freezes_used=0)

    gap_days = (today - last_checkin_date).days
    if gap_days == 1:
        return StreakUpdate(already_checked_in=False, new_streak=streak_count + 1, freezes_used=0)
    if gap_days == 2 and streak_freezes > 0:
        # Missed exactly one day, but a freeze covers it (plan: "gap is at
        # most 2 days" — gap 0/1 are handled above, so this branch is gap==2).
        return StreakUpdate(already_checked_in=False, new_streak=streak_count + 1, freezes_used=1)
    return StreakUpdate(already_checked_in=False, new_streak=1, freezes_used=0)


def checkin_xp(new_streak: int) -> int:
    """10 + 5*min(streak-1, 6); +50 bonus on every 7th consecutive day (plan section 9.2)."""
    base = 10 + 5 * min(new_streak - 1, 6)
    bonus = 50 if new_streak % 7 == 0 else 0
    return base + bonus


def today_utc() -> date:
    return datetime.now(UTC).date()


async def do_checkin(db, user) -> dict:
    """DB-touching half: applies compute_streak_update's result, awards XP
    via the ledger with idempotency key `checkin:<user>:<date>` (plan
    section 11), and updates the user row. Import-local to avoid a circular
    import with app.models.user at module load time in some orderings."""
    from sqlalchemy.exc import IntegrityError

    from app.models.xp_event import XpEvent
    from app.services.achievements import check_achievements
    from app.services.notifications import queue_notification
    from app.services.seasons import active_season_id
    from app.services.xp import level_for_xp

    today = today_utc()
    update = compute_streak_update(user.last_checkin_date, today, user.streak_count, user.streak_freezes)

    if update.already_checked_in:
        return {
            "checked_in_today": True,
            "streak_count": user.streak_count,
            "streak_freezes": user.streak_freezes,
            "last_checkin_date": user.last_checkin_date,
            "xp_awarded": 0,
            "total_xp": user.total_xp,
            "level": user.level,
        }

    xp = checkin_xp(update.new_streak)
    user.streak_count = update.new_streak
    user.streak_freezes -= update.freezes_used
    user.last_checkin_date = today

    db.add(XpEvent(
        user_id=user.id, source="checkin", amount=xp,
        ref_type="checkin", ref_id=today.isoformat(),
        idempotency_key=f"checkin:{user.id}:{today.isoformat()}",
        season_id=await active_season_id(db),
    ))
    previous_level = user.level
    user.total_xp += xp
    user.level = level_for_xp(user.total_xp)
    if user.level > previous_level:
        queue_notification(db, user.id, "level_up", {"level": user.level})
    try:
        await db.commit()
    except IntegrityError:
        # Two concurrent check-in calls raced past the already_checked_in
        # check above before either committed; the idempotency_key unique
        # constraint is the backstop. Whoever loses just sees "already
        # checked in" with today's real (winning) state.
        await db.rollback()
        await db.refresh(user)
        return {
            "checked_in_today": True,
            "streak_count": user.streak_count,
            "streak_freezes": user.streak_freezes,
            "last_checkin_date": user.last_checkin_date,
            "xp_awarded": 0,
            "total_xp": user.total_xp,
            "level": user.level,
        }

    newly_unlocked = await check_achievements(db, user)  # checked_in event (plan section 11)

    return {
        "checked_in_today": True,
        "streak_count": user.streak_count,
        "streak_freezes": user.streak_freezes,
        "last_checkin_date": user.last_checkin_date,
        "xp_awarded": xp,
        "total_xp": user.total_xp,
        "level": user.level,
        "new_achievements": [a.key for a in newly_unlocked],
    }
