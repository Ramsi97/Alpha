import math

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.core.db import get_db
from app.core.errors import ApiError
from app.core.redis import get_redis
from app.models.game import Game
from app.models.user import User
from app.schemas.leaderboard import LeaderboardEntry, LeaderboardOut
from app.services import leaderboard as lb
from app.services.friends import friend_ids
from app.services.seasons import get_active_season, season_standings

router = APIRouter()


async def _build_response(redis, db: AsyncSession, key: str, user: User, limit: int) -> LeaderboardOut:
    top = await lb.get_top(redis, key, limit)
    user_ids = [uid for uid, _ in top]
    users_by_id: dict[int, User] = {}
    if user_ids:
        rows = (await db.execute(select(User).where(User.id.in_(user_ids)))).scalars().all()
        users_by_id = {u.id: u for u in rows}

    entries = [
        LeaderboardEntry(
            rank=i + 1,
            user_id=uid,
            username=users_by_id[uid].username if uid in users_by_id else None,
            first_name=users_by_id[uid].first_name if uid in users_by_id else None,
            score=math.floor(score),  # strip the tie-break fraction added for game leaderboards
        )
        for i, (uid, score) in enumerate(top)
    ]

    my_rank = await lb.get_rank(redis, key, user.id)
    my_score_raw = await redis.zscore(key, str(user.id))
    my_score = math.floor(my_score_raw) if my_score_raw is not None else None

    return LeaderboardOut(entries=entries, my_rank=my_rank, my_score=my_score)


@router.get("/leaderboards/xp", response_model=LeaderboardOut)
async def leaderboard_xp(
    limit: int = Query(default=100, le=200),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LeaderboardOut:
    return await _build_response(get_redis(), db, lb.xp_leaderboard_key(), user, limit)


@router.get("/leaderboards/games/{slug}", response_model=LeaderboardOut)
async def leaderboard_game(
    slug: str,
    variant: str | None = None,
    limit: int = Query(default=100, le=200),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LeaderboardOut:
    game = (await db.execute(select(Game).where(Game.slug == slug, Game.status == "active"))).scalar_one_or_none()
    if game is None:
        raise ApiError(404, "not_found", f"No active game with slug '{slug}'.")
    key = lb.game_leaderboard_key(game.id, variant)
    return await _build_response(get_redis(), db, key, user, limit)


@router.get("/leaderboards/friends", response_model=LeaderboardOut)
async def leaderboard_friends(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LeaderboardOut:
    ids = await friend_ids(db, user.id)
    ids.add(user.id)
    rows = (
        await db.execute(select(User).where(User.id.in_(ids)).order_by(User.total_xp.desc(), User.id))
    ).scalars().all()

    entries = [
        LeaderboardEntry(rank=i + 1, user_id=u.id, username=u.username, first_name=u.first_name, score=u.total_xp)
        for i, u in enumerate(rows)
    ]
    my_entry = next((e for e in entries if e.user_id == user.id), None)
    return LeaderboardOut(
        entries=entries, my_rank=my_entry.rank if my_entry else None, my_score=my_entry.score if my_entry else None
    )


@router.get("/leaderboards/season", response_model=LeaderboardOut)
async def leaderboard_season(
    limit: int = Query(default=100, le=200),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LeaderboardOut:
    season = await get_active_season(db)
    if season is None:
        raise ApiError(404, "no_active_season", "There is no active season right now.")

    standings = await season_standings(db, season.id)
    user_ids = [uid for uid, _ in standings[:limit]]
    users_by_id: dict[int, User] = {}
    if user_ids:
        rows = (await db.execute(select(User).where(User.id.in_(user_ids)))).scalars().all()
        users_by_id = {u.id: u for u in rows}

    entries = [
        LeaderboardEntry(
            rank=i + 1, user_id=uid,
            username=users_by_id[uid].username if uid in users_by_id else None,
            first_name=users_by_id[uid].first_name if uid in users_by_id else None,
            score=score,
        )
        for i, (uid, score) in enumerate(standings[:limit])
    ]
    my_entry = next((e for e in entries if e.user_id == user.id), None)
    if my_entry is None:
        my_rank_full = next((i + 1 for i, (uid, _) in enumerate(standings) if uid == user.id), None)
        my_score_full = next((s for uid, s in standings if uid == user.id), None)
    else:
        my_rank_full, my_score_full = my_entry.rank, my_entry.score

    return LeaderboardOut(entries=entries, my_rank=my_rank_full, my_score=my_score_full)
