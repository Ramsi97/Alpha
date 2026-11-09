"""Recomputes games.trending_score (plan section 6/15).

Usage: python -m app.workers.update_trending
Idempotent: a plain recompute from game_sessions, safe to re-run on a
schedule (e.g. hourly). Trending = number of finished sessions in the last
3 days, so a game that was popular last month but is quiet now sinks back
down rather than sitting at the top forever.
"""

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.core.db import SessionLocal
from app.models.game import Game
from app.models.session import GameSession

TRENDING_WINDOW_DAYS = 3


async def update_trending() -> None:
    cutoff = datetime.now(UTC) - timedelta(days=TRENDING_WINDOW_DAYS)
    async with SessionLocal() as db:
        counts = dict(
            (
                await db.execute(
                    select(GameSession.game_id, func.count())
                    .where(GameSession.status == "finished", GameSession.finished_at >= cutoff)
                    .group_by(GameSession.game_id)
                )
            ).all()
        )
        games = (await db.execute(select(Game))).scalars().all()
        for game in games:
            game.trending_score = counts.get(game.id, 0)
        await db.commit()
        print(f"updated trending_score for {len(games)} games")


if __name__ == "__main__":
    asyncio.run(update_trending())
