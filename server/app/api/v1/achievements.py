from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.core.db import get_db
from app.models.achievement import Achievement, UserAchievement
from app.models.user import User
from app.schemas.achievement import AchievementOut

router = APIRouter()


@router.get("/achievements", response_model=list[AchievementOut])
async def list_achievements(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AchievementOut]:
    achievements = (await db.execute(select(Achievement).order_by(Achievement.id))).scalars().all()
    unlocked_rows = (
        await db.execute(select(UserAchievement).where(UserAchievement.user_id == user.id))
    ).scalars().all()
    unlocked_at_by_id = {row.achievement_id: row.unlocked_at for row in unlocked_rows}

    return [
        AchievementOut(
            key=a.key, title=a.title, description=a.description, icon=a.icon, xp_reward=a.xp_reward,
            unlocked=a.id in unlocked_at_by_id,
            unlocked_at=unlocked_at_by_id.get(a.id),
        )
        for a in achievements
    ]
