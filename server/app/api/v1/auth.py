from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import get_db
from app.core.errors import ApiError
from app.core.rate_limit import rate_limit
from app.core.security import InitDataError, issue_jwt, validate_init_data
from app.schemas.auth import AuthRequest, AuthResponse
from app.services.auth import ensure_admin_bootstrap, get_or_create_user
from app.services.profile import build_user_out

router = APIRouter()


@router.post(
    "/auth/telegram",
    response_model=AuthResponse,
    dependencies=[rate_limit("auth", limit=30, window_seconds=3600)],  # plan section 17: per-IP auth limit
)
async def auth_telegram(body: AuthRequest, db: AsyncSession = Depends(get_db)) -> AuthResponse:
    try:
        parsed = validate_init_data(body.init_data, settings.bot_token, settings.initdata_max_age_seconds)
    except InitDataError as e:
        raise ApiError(401, "invalid_init_data", str(e)) from e

    user = await get_or_create_user(db, parsed["user"], parsed["start_param"])
    await db.commit()
    await ensure_admin_bootstrap(db, user)

    token, ttl = issue_jwt(user.id, user.telegram_id)
    return AuthResponse(access_token=token, expires_in=ttl, user=await build_user_out(db, user))
