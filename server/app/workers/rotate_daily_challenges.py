"""Rotates daily/weekly "challenge" tasks (plan section 21/B5: "Daily/weekly
challenges with rotation job").

This reuses the existing task engine (plan section 12) rather than adding a
parallel system: a "rotating challenge" is just an ordinary `play_game`
Task with `period='daily'` or `'weekly'` and `payload.rotates = true` set
by an admin up front. What this job does each run is pick a *new*
game+target for that Task's payload once per period, so players get a
different daily/weekly goal instead of the same one forever — completion
tracking itself already works for free via the existing `period_key` on
UserTask (a new day/week == a fresh completion slot with no code change).

Usage: python -m app.workers.rotate_daily_challenges
Idempotent per period: a task only rotates once per UTC day (or ISO week),
tracked in `payload.rotated_on`; re-running this mid-period is a no-op for
any task already rotated. Run on a schedule (e.g. hourly cron) — most runs
will find nothing due.
"""

import asyncio
import random
from datetime import UTC, datetime

from sqlalchemy import select

from app.core.db import SessionLocal
from app.models.game import Game
from app.models.task import Task
from app.services.tasks import period_key_for

TARGET_FRACTION_OF_MAX_SCORE = 0.1  # a round, conservative target — not tuned against real play data yet


async def _pick_new_target(db) -> tuple[str, int] | None:
    games = (await db.execute(select(Game).where(Game.status == "active"))).scalars().all()
    if not games:
        return None
    game = random.choice(games)
    target = max(1, int(game.max_score * TARGET_FRACTION_OF_MAX_SCORE))
    return game.slug, target


async def rotate() -> None:
    now = datetime.now(UTC)
    async with SessionLocal() as db:
        tasks = (
            await db.execute(select(Task).where(Task.active == True, Task.type == "play_game"))  # noqa: E712
        ).scalars().all()

        rotated = 0
        for task in tasks:
            payload = task.payload or {}
            if not payload.get("rotates"):
                continue
            period_key = period_key_for(task.period, now)
            if payload.get("rotated_on") == period_key:
                continue  # already rotated for this period

            picked = await _pick_new_target(db)
            if picked is None:
                continue
            game_slug, target = picked
            task.payload = {**payload, "game_slug": game_slug, "min_score": target, "rotated_on": period_key}
            rotated += 1

        await db.commit()
        print(f"rotated {rotated} task(s)")


if __name__ == "__main__":
    asyncio.run(rotate())
