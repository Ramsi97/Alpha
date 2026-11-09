from datetime import datetime

from pydantic import BaseModel


class TournamentOut(BaseModel):
    id: int
    title: dict
    game_slug: str
    variant: str | None
    rule: str
    top_n: int | None
    starts_at: datetime
    ends_at: datetime
    status: str
    my_score: int | None = None
    my_rank: int | None = None


class TournamentCreateRequest(BaseModel):
    title: dict
    game_slug: str
    variant: str | None = None
    rule: str = "best_score"
    top_n: int | None = None
    starts_at: datetime
    ends_at: datetime


class TournamentEntryOut(BaseModel):
    rank: int | None
    user_id: int
    username: str | None
    first_name: str | None
    score: int
