"""Closes any tournament whose ends_at has passed (plan section 13).

Usage: python -m app.workers.close_tournaments
Idempotent per tournament: close_tournament() sets status='ended'. Run on
a schedule (e.g. hourly cron).
"""

import asyncio
from datetime import UTC, datetime

from sqlalchemy import select

from app.core.db import SessionLocal
from app.models.tournament import Tournament
from app.services.tournaments import close_tournament


async def close_due_tournaments() -> None:
    now = datetime.now(UTC)
    async with SessionLocal() as db:
        due = (
            await db.execute(select(Tournament).where(Tournament.status == "active", Tournament.ends_at <= now))
        ).scalars().all()
        for tournament in due:
            await close_tournament(db, tournament)
            print(f"closed tournament {tournament.id}")
        if not due:
            print("no tournaments due")


if __name__ == "__main__":
    asyncio.run(close_due_tournaments())
