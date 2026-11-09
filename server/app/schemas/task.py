from datetime import datetime

from pydantic import BaseModel


class TaskOut(BaseModel):
    id: int
    type: str
    title: dict
    description: dict | None
    xp_reward: int
    period: str
    verify_method: str
    status: str | None  # this period's UserTask status, or None if never started


class VerifyResultOut(BaseModel):
    status: str
    xp_awarded: int = 0


class AdminTaskCreate(BaseModel):
    type: str
    title: dict
    description: dict | None = None
    payload: dict = {}
    xp_reward: int
    period: str = "once"
    verify_method: str
    sponsor_id: int | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    max_total_completions: int | None = None
    active: bool = True


class AdminTaskOut(AdminTaskCreate):
    id: int


class AdminTaskPatch(BaseModel):
    title: dict | None = None
    description: dict | None = None
    payload: dict | None = None
    xp_reward: int | None = None
    active: bool | None = None
    ends_at: datetime | None = None
    max_total_completions: int | None = None


class AdminUserTaskOut(BaseModel):
    id: int
    user_id: int
    task_id: int
    period_key: str
    status: str
    started_at: datetime
    completed_at: datetime | None
