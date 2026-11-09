"""Seasons (plan section 13): season id on every ledger row, a season
leaderboard, and an end-of-season job that freezes results, pays out
rank-based XP, and starts the next season.

The season leaderboard is read straight from Postgres (sum of xp_events
for the active season, grouped by user) rather than a Redis sorted set —
the plan itself calls the Redis version "rebuildable" from this same
ledger, and a season only needs to be fast to read, not real-time-ranked
on every single XP grant the way the global/per-game leaderboards are.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.season import Season, SeasonResult
from app.models.xp_event import XpEvent
from app.services.notifications import queue_notification
from app.services.settings_store import get_setting
from app.services.xp import level_for_xp

DEFAULT_SEASON_DURATION_DAYS = 30
DEFAULT_SEASON_RANK_XP = {"1": 500, "2": 300, "3": 150}  # JSON keys are strings (settings are JSONB)


async def active_season_id(db: AsyncSession) -> int | None:
    season = (await db.execute(select(Season).where(Season.status == "active"))).scalar_one_or_none()
    return season.id if season else None


async def get_active_season(db: AsyncSession) -> Season | None:
    return (await db.execute(select(Season).where(Season.status == "active"))).scalar_one_or_none()


async def season_standings(db: AsyncSession, season_id: int, limit: int | None = None) -> list[tuple[int, int]]:
    """[(user_id, season_xp), ...] ordered highest first."""
    query = (
        select(XpEvent.user_id, func.sum(XpEvent.amount))
        .where(XpEvent.season_id == season_id)
        .group_by(XpEvent.user_id)
        .order_by(func.sum(XpEvent.amount).desc())
    )
    if limit is not None:
        query = query.limit(limit)
    rows = (await db.execute(query)).all()
    return [(user_id, int(total)) for user_id, total in rows]


async def start_season(db: AsyncSession, name: str, starts_at: datetime, ends_at: datetime) -> Season:
    season = Season(name=name, starts_at=starts_at, ends_at=ends_at, status="active")
    db.add(season)
    await db.flush()
    return season


async def close_season(db: AsyncSession, season: Season) -> list[SeasonResult]:
    """Freezes standings into season_results, pays rank-based XP (plan
    section 13: "award badges/XP to ranks" — no separate badge system
    exists yet, so this is XP-only; see README), and starts the next
    season back-to-back so there's never a gap with no active season."""
    from app.models.user import User  # local import avoids a cycle with sessions.py -> ... -> seasons.py

    standings = await season_standings(db, season.id)
    rank_xp = await get_setting(db, "season_rank_xp", DEFAULT_SEASON_RANK_XP)

    results: list[SeasonResult] = []
    for i, (user_id, season_xp) in enumerate(standings):
        rank = i + 1
        awarded = int(rank_xp.get(str(rank), 0))
        if awarded > 0:
            user = (await db.execute(select(User).where(User.id == user_id))).scalar_one()
            db.add(XpEvent(
                user_id=user_id, source="season", amount=awarded,
                ref_type="season_rank", ref_id=str(season.id),
                idempotency_key=f"season_rank:{season.id}:{user_id}",
            ))
            user.total_xp += awarded
            user.level = level_for_xp(user.total_xp)
            queue_notification(db, user_id, "season_end", {"rank": rank})
        results.append(SeasonResult(season_id=season.id, user_id=user_id, rank=rank, season_xp=season_xp, xp_awarded=awarded))

    db.add_all(results)
    season.status = "ended"

    duration_days = await get_setting(db, "season_duration_days", DEFAULT_SEASON_DURATION_DAYS)
    now = datetime.now(UTC)
    next_number = int(season.name.split()[-1]) + 1 if season.name.split()[-1].isdigit() else 1
    await start_season(db, f"Season {next_number}", now, now + timedelta(days=duration_days))

    await db.commit()
    return results
