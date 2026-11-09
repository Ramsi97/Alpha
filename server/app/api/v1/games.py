from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.core.db import get_db
from app.core.errors import ApiError
from app.models.game import Game
from app.models.score import Score
from app.models.user import User
from app.schemas.favorite import RatingRequest
from app.schemas.game import GameDetailOut, GameOut
from app.services.favorites import (
    add_favorite,
    average_ratings,
    favorite_game_ids,
    recently_played_game_ids,
    remove_favorite,
    submit_rating,
)

router = APIRouter()


async def _best_scores_by_game(db: AsyncSession, user_id: int) -> dict[int, int]:
    rows = (
        await db.execute(
            select(Score.game_id, Score.value)
            .where(Score.user_id == user_id)
            .order_by(Score.game_id, Score.value.desc())
        )
    ).all()
    best: dict[int, int] = {}
    for game_id, value in rows:
        best.setdefault(game_id, value)  # first row per game_id is the max, thanks to the ORDER BY
    return best


@router.get("/games", response_model=list[GameOut])
async def list_games(
    category: str | None = None,
    sort_by: str = Query(default="default", pattern="^(default|trending)$"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[GameOut]:
    query = select(Game).where(Game.status == "active")
    if category is not None:
        query = query.where(Game.category == category)
    query = query.order_by(Game.trending_score.desc(), Game.slug) if sort_by == "trending" else query.order_by(Game.slug)

    games = (await db.execute(query)).scalars().all()
    best = await _best_scores_by_game(db, user.id)
    favorites = await favorite_game_ids(db, user.id)
    recently_played = await recently_played_game_ids(db, user.id)
    ratings = await average_ratings(db, [g.id for g in games])
    out = []
    for g in games:
        item = GameOut.model_validate(g)
        item.best_score = best.get(g.id)
        item.is_favorite = g.id in favorites
        item.recently_played = g.id in recently_played
        item.average_rating = ratings.get(g.id)
        out.append(item)
    return out


@router.get("/games/{slug}", response_model=GameDetailOut)
async def get_game(
    slug: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> GameDetailOut:
    game = (await db.execute(select(Game).where(Game.slug == slug, Game.status == "active"))).scalar_one_or_none()
    if game is None:
        raise ApiError(404, "not_found", f"No active game with slug '{slug}'.")
    best = await _best_scores_by_game(db, user.id)
    out = GameDetailOut.model_validate(game)
    out.best_score = best.get(game.id)
    out.is_favorite = game.id in await favorite_game_ids(db, user.id)
    out.recently_played = game.id in await recently_played_game_ids(db, user.id)
    out.average_rating = (await average_ratings(db, [game.id])).get(game.id)
    return out


async def _active_game_or_404(db: AsyncSession, slug: str) -> Game:
    game = (await db.execute(select(Game).where(Game.slug == slug, Game.status == "active"))).scalar_one_or_none()
    if game is None:
        raise ApiError(404, "not_found", f"No active game with slug '{slug}'.")
    return game


@router.post("/games/{slug}/favorite", status_code=204)
async def post_favorite(
    slug: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> None:
    game = await _active_game_or_404(db, slug)
    await add_favorite(db, user.id, game.id)


@router.delete("/games/{slug}/favorite", status_code=204)
async def delete_favorite(
    slug: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> None:
    game = await _active_game_or_404(db, slug)
    await remove_favorite(db, user.id, game.id)


@router.post("/games/{slug}/rating", status_code=204)
async def post_rating(
    slug: str, body: RatingRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> None:
    game = await _active_game_or_404(db, slug)
    await submit_rating(db, user.id, game.id, body.rating)
