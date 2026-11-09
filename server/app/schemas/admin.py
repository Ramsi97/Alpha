from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AdminUserOut(BaseModel):
    id: int
    telegram_id: int
    username: str | None
    first_name: str | None
    total_xp: int
    level: int
    is_banned: bool
    bot_blocked: bool
    created_at: datetime


class AdminXpAdjustRequest(BaseModel):
    amount: int  # can be negative
    reason: str
    idempotency_key: str | None = None  # defaults to a fresh uuid if omitted


class AdminScoreOut(BaseModel):
    id: int
    user_id: int
    game_id: int
    variant: str | None
    value: int
    xp_awarded: int
    created_at: datetime


class AdminGamePatch(BaseModel):
    status: str | None = None  # 'pending' | 'active' | 'disabled'
    xp_rate: float | None = None
    max_xp_per_run: int | None = None
    max_score_per_second: float | None = None
    min_play_seconds: int | None = None


class SettingOut(BaseModel):
    key: str
    value: Any


class SettingPut(BaseModel):
    value: Any
