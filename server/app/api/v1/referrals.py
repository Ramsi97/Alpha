from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.core.config import settings
from app.core.db import get_db
from app.models.referral import Referral
from app.models.user import User
from app.schemas.referral import ReferralsOut

router = APIRouter()


@router.get("/referrals", response_model=ReferralsOut)
async def get_referrals(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> ReferralsOut:
    # Deep link shape per plan section 12.4.
    link = f"https://t.me/{settings.bot_username}/{settings.mini_app_short_name}?startapp=r_{user.referral_code}"

    pending = (
        await db.execute(
            select(func.count()).select_from(Referral).where(
                Referral.referrer_id == user.id, Referral.status == "pending"
            )
        )
    ).scalar_one()
    rewarded = (
        await db.execute(
            select(func.count()).select_from(Referral).where(
                Referral.referrer_id == user.id, Referral.status == "rewarded"
            )
        )
    ).scalar_one()

    return ReferralsOut(
        referral_code=user.referral_code, referral_link=link, pending_count=pending, rewarded_count=rewarded
    )
