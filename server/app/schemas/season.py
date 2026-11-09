from datetime import datetime

from pydantic import BaseModel


class SeasonOut(BaseModel):
    id: int
    name: str
    starts_at: datetime
    ends_at: datetime
    status: str


class SeasonCreateRequest(BaseModel):
    name: str
    starts_at: datetime
    ends_at: datetime
