import uuid

from pydantic import BaseModel


class SessionCreateRequest(BaseModel):
    variant: str | None = None


class SessionCreateResponse(BaseModel):
    session_id: uuid.UUID
    token: str
    seed: str
    variant: str | None


class SessionFinishRequest(BaseModel):
    token: str
    score: int
    variant: str | None = None
    meta: dict | None = None


class LevelProgress(BaseModel):
    current_level_xp: int   # XP earned since the start of the current level
    xp_for_next_level: int  # total XP span of the current level


class SessionFinishResponse(BaseModel):
    score: int
    xp_awarded: int
    total_xp: int
    level: int
    level_progress: LevelProgress
    personal_best: int
    rank: int | None
    new_achievements: list[str] = []
    flagged: bool = False
