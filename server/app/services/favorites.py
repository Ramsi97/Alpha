"""Favorites, recently-played, and ratings (plan sections 7 and 15)."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.favorite import Favorite, GameRating
from app.models.session import GameSession

RECENTLY_PLAYED_WINDOW_DAYS = 14


async def add_favorite(db: AsyncSession, user_id: int, game_id: int) -> None:
    stmt = pg_insert(Favorite).values(user_id=user_id, game_id=game_id).on_conflict_do_nothing()
    await db.execute(stmt)
    await db.commit()


async def remove_favorite(db: AsyncSession, user_id: int, game_id: int) -> None:
    await db.execute(Favorite.__table__.delete().where(Favorite.user_id == user_id, Favorite.game_id == game_id))
    await db.commit()


async def favorite_game_ids(db: AsyncSession, user_id: int) -> set[int]:
    rows = (await db.execute(select(Favorite.game_id).where(Favorite.user_id == user_id))).scalars().all()
    return set(rows)


async def recently_played_game_ids(db: AsyncSession, user_id: int) -> set[int]:
    cutoff = datetime.now(UTC) - timedelta(days=RECENTLY_PLAYED_WINDOW_DAYS)
    rows = (
        await db.execute(
            select(GameSession.game_id).distinct().where(
                GameSession.user_id == user_id, GameSession.status == "finished", GameSession.finished_at >= cutoff
            )
        )
    ).scalars().all()
    return set(rows)


async def submit_rating(db: AsyncSession, user_id: int, game_id: int, rating: int) -> None:
    # One rating per user per game; a later call replaces the earlier one
    # rather than creating a second row (the primary key is (user_id, game_id)).
    stmt = (
        pg_insert(GameRating)
        .values(user_id=user_id, game_id=game_id, rating=rating)
        .on_conflict_do_update(index_elements=["user_id", "game_id"], set_={"rating": rating})
    )
    await db.execute(stmt)
    await db.commit()


async def average_ratings(db: AsyncSession, game_ids: list[int]) -> dict[int, float]:
    if not game_ids:
        return {}
    rows = (
        await db.execute(
            select(GameRating.game_id, func.avg(GameRating.rating))
            .where(GameRating.game_id.in_(game_ids))
            .group_by(GameRating.game_id)
        )
    ).all()
    return {game_id: float(avg) for game_id, avg in rows}
