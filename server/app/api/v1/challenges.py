from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.core.config import settings
from app.core.db import get_db
from app.core.errors import ApiError
from app.models.game import Game
from app.models.user import User
from app.schemas.challenge import ChallengeCreateRequest, ChallengeOut
from app.services.challenges import create_challenge, get_active_challenge_by_token

router = APIRouter()


def _share_link(token: str) -> str:
    return f"https://t.me/{settings.bot_username}/{settings.mini_app_short_name}?startapp=c_{token}"


async def _to_out(db: AsyncSession, challenge) -> ChallengeOut:
    game = (await db.execute(select(Game).where(Game.id == challenge.game_id))).scalar_one()
    challenger = (await db.execute(select(User).where(User.id == challenge.challenger_id))).scalar_one_or_none()
    return ChallengeOut(
        token=challenge.token, game_slug=game.slug, variant=challenge.variant,
        score_to_beat=challenge.score_to_beat,
        challenger_name=challenger.first_name if challenger else None,
        expires_at=challenge.expires_at, share_link=_share_link(challenge.token),
    )


@router.post("/challenges", response_model=ChallengeOut)
async def post_challenge(
    body: ChallengeCreateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChallengeOut:
    game = (await db.execute(select(Game).where(Game.slug == body.game_slug, Game.status == "active"))).scalar_one_or_none()
    if game is None:
        raise ApiError(404, "not_found", f"No active game with slug '{body.game_slug}'.")
    challenge = await create_challenge(db, user, game.id, body.variant, body.score_to_beat)
    await db.commit()
    return await _to_out(db, challenge)


@router.get("/challenges/{token}", response_model=ChallengeOut)
async def get_challenge(
    token: str,
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChallengeOut:
    challenge = await get_active_challenge_by_token(db, token)
    if challenge is None:
        raise ApiError(404, "not_found", "No active challenge with that token.")
    return await _to_out(db, challenge)
