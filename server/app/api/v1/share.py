from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.core.db import get_db
from app.core.errors import ApiError
from app.models.user import User
from app.schemas.share import ScoreCardOut, ScoreCardRequest
from app.services.score_card import build_score_card

router = APIRouter()


@router.post("/share/score-card", response_model=ScoreCardOut)
async def post_score_card(
    body: ScoreCardRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ScoreCardOut:
    try:
        url = await build_score_card(db, user, body.game_slug, body.variant, body.score)
    except ValueError as e:
        raise ApiError(404, "not_found", str(e))
    return ScoreCardOut(url=url)
