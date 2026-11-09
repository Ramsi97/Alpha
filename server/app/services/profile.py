from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.achievement import UserAchievement
from app.models.user import User
from app.schemas.user import UserOut
from app.services.xp import level_progress


async def build_user_out(db: AsyncSession, user: User) -> UserOut:
    """UserOut with the fields that aren't plain columns (level_progress,
    achievements_unlocked) filled in — the same "validate then patch"
    pattern as GameOut.best_score, so every endpoint returning a user
    profile looks consistent (plan section 15: `/me` is "Profile, XP,
    level, streak, badges summary")."""
    out = UserOut.model_validate(user)
    out.level_progress = level_progress(user.total_xp, user.level)
    out.achievements_unlocked = (
        await db.execute(select(func.count()).select_from(UserAchievement).where(UserAchievement.user_id == user.id))
    ).scalar_one()
    return out
