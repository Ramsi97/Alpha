from datetime import datetime

from pydantic import BaseModel


class AchievementOut(BaseModel):
    key: str
    title: dict
    description: dict | None
    icon: str | None
    xp_reward: int
    unlocked: bool
    unlocked_at: datetime | None = None
