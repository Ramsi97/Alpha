"""Closes any season whose ends_at has passed (plan section 13).

Usage: python -m app.workers.end_season
Idempotent per season: close_season() sets status='ended', so a season
already closed is simply not selected on the next run. Run on a schedule
(e.g. hourly cron) — most runs will find nothing to do.
"""

import asyncio
from datetime import UTC, datetime

from sqlalchemy import select

from app.core.db import SessionLocal
from app.models.season import Season
from app.services.seasons import close_season


async def end_due_seasons() -> None:
    now = datetime.now(UTC)
    async with SessionLocal() as db:
        due = (
            await db.execute(select(Season).where(Season.status == "active", Season.ends_at <= now))
        ).scalars().all()
        for season in due:
            await close_season(db, season)
            print(f"closed season {season.id} ({season.name})")
        if not due:
            print("no seasons due")


if __name__ == "__main__":
    asyncio.run(end_due_seasons())
