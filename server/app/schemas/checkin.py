from datetime import date

from pydantic import BaseModel


class CheckinStatus(BaseModel):
    checked_in_today: bool
    streak_count: int
    streak_freezes: int
    last_checkin_date: date | None


class CheckinResult(CheckinStatus):
    xp_awarded: int
    total_xp: int
    level: int
    new_achievements: list[str] = []
