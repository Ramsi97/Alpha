from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.core.db import get_db
from app.models.user import User
from app.schemas.checkin import CheckinResult, CheckinStatus
from app.services.checkin import do_checkin, today_utc

router = APIRouter()


@router.get("/checkin", response_model=CheckinStatus)
async def checkin_status(user: User = Depends(get_current_user)) -> CheckinStatus:
    return CheckinStatus(
        checked_in_today=user.last_checkin_date == today_utc(),
        streak_count=user.streak_count,
        streak_freezes=user.streak_freezes,
        last_checkin_date=user.last_checkin_date,
    )


@router.post("/checkin", response_model=CheckinResult)
async def checkin(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CheckinResult:
    result = await do_checkin(db, user)
    return CheckinResult(**result)
