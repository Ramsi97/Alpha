from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.core.db import get_db
from app.core.errors import ApiError
from app.models.user import User
from app.models.xp_event import XpEvent
from app.schemas.user import UserOut, UserPatch
from app.schemas.xp_history import XpHistoryEntry, XpHistoryPage
from app.services.account_deletion import delete_account
from app.services.profile import build_user_out

router = APIRouter()


@router.get("/me", response_model=UserOut)
async def get_me(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> UserOut:
    return await build_user_out(db, user)


@router.patch("/me", response_model=UserOut)
async def patch_me(
    body: UserPatch,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    if body.language is not None:
        user.language = body.language
    if body.notifications_enabled is not None:
        user.notifications_enabled = body.notifications_enabled
    await db.commit()
    return await build_user_out(db, user)


@router.delete("/me", status_code=204)
async def delete_me(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> None:
    """Plan section 18: "a simple data-deletion path for users who ask."
    Anonymizes PII and marks the account deleted; the row and its ledger
    history (scores, xp_events) stay, same as every other "never delete,
    only mark" pattern already used in this backend. Re-opening the Mini
    App afterward (fresh initData) reverses this — see
    app/services/auth.py:get_or_create_user."""
    await delete_account(db, user)


@router.get("/me/xp-history", response_model=XpHistoryPage)
async def xp_history(
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> XpHistoryPage:
    # Cursor is just the last-seen XpEvent.id, newest-first (ids are a
    # BIGSERIAL, strictly increasing — a valid total order to page on).
    # "Opaque" to the client in the sense that it shouldn't need to
    # understand it, not that it's encrypted; plan section 15 just asks
    # for "opaque cursors" generically.
    query = select(XpEvent).where(XpEvent.user_id == user.id)
    if cursor is not None:
        try:
            cursor_id = int(cursor)
        except ValueError:
            raise ApiError(400, "invalid_cursor", "Cursor is not valid.")
        query = query.where(XpEvent.id < cursor_id)
    query = query.order_by(XpEvent.id.desc()).limit(limit)

    rows = (await db.execute(query)).scalars().all()
    next_cursor = str(rows[-1].id) if len(rows) == limit else None

    return XpHistoryPage(
        entries=[XpHistoryEntry.model_validate(r, from_attributes=True) for r in rows],
        next_cursor=next_cursor,
    )
