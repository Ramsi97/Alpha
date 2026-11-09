from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.schemas.session import LevelProgress


class UserOut(BaseModel):
    # validate_assignment=True: level_progress/achievements_unlocked are
    # set via plain attribute assignment after model_validate() (see
    # app/services/profile.py), which pydantic v2 otherwise skips
    # validation/coercion for — caught a real bug this way (a raw dict
    # sitting in the LevelProgress-typed field instead of being coerced).
    model_config = ConfigDict(from_attributes=True, validate_assignment=True)

    id: int
    telegram_id: int
    username: str | None
    first_name: str | None
    language: str
    total_xp: int
    level: int
    streak_count: int
    last_checkin_date: date | None
    referral_code: str
    # Not derivable from the User row alone — populated by the endpoint
    # after model_validate(), same pattern as GameOut.best_score.
    level_progress: LevelProgress | None = None
    achievements_unlocked: int = 0


class UserPatch(BaseModel):
    # Plan section 21/B5: the three supported languages (Afaan Oromo,
    # Amharic, English). `users.language` itself stays a plain string
    # (signup takes whatever Telegram's language_code says, unrestricted —
    # see app/services/auth.py), but a user explicitly picking their own
    # language through this endpoint can only choose one we actually have
    # templates for.
    language: Literal["en", "am", "om"] | None = None
    notifications_enabled: bool | None = None
