from datetime import datetime

from pydantic import BaseModel


class ChallengeCreateRequest(BaseModel):
    game_slug: str
    variant: str | None = None
    score_to_beat: int


class ChallengeOut(BaseModel):
    token: str
    game_slug: str
    variant: str | None
    score_to_beat: int
    challenger_name: str | None
    expires_at: datetime
    share_link: str
