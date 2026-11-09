from pydantic import BaseModel


class LeaderboardEntry(BaseModel):
    rank: int
    user_id: int
    username: str | None
    first_name: str | None
    score: int


class LeaderboardOut(BaseModel):
    entries: list[LeaderboardEntry]
    my_rank: int | None
    my_score: int | None
