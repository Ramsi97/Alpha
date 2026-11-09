from pydantic import BaseModel


class ScoreCardRequest(BaseModel):
    game_slug: str
    variant: str | None = None
    score: int


class ScoreCardOut(BaseModel):
    url: str
