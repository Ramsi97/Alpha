from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.errors import ApiError
from app.core.security import TokenError, decode_jwt
from app.models.admin import AdminUser
from app.models.user import User


async def get_current_user(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise ApiError(401, "unauthorized", "Missing or malformed Authorization header.")
    token = authorization.split(" ", 1)[1]
    try:
        payload = decode_jwt(token)
    except TokenError as e:
        raise ApiError(401, "unauthorized", str(e)) from e

    user_id = int(payload["sub"])
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        raise ApiError(401, "unauthorized", "User not found.")
    if user.deleted_at is not None:
        # A JWT issued before deletion is still cryptographically valid
        # until it naturally expires (short TTL — see app/core/security.py)
        # — reject it explicitly rather than let a stale token keep acting
        # as a "deleted" account for up to another hour.
        raise ApiError(401, "unauthorized", "This account has been deleted.")
    if user.is_banned:
        raise ApiError(403, "banned", "This account is banned.")
    return user


async def require_admin(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Plan section 16: admin access needs the same initData->JWT auth AND
    an admin_users row (bootstrapped from ADMIN_TELEGRAM_IDS on login, see
    app/services/auth.py:ensure_admin_bootstrap)."""
    is_admin = (await db.execute(select(AdminUser).where(AdminUser.user_id == user.id))).scalar_one_or_none()
    if is_admin is None:
        raise ApiError(403, "forbidden", "Admin access required.")
    return user
