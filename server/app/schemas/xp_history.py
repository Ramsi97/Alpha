from datetime import datetime

from pydantic import BaseModel


class XpHistoryEntry(BaseModel):
    id: int
    source: str
    amount: int
    ref_type: str | None
    ref_id: str | None
    created_at: datetime


class XpHistoryPage(BaseModel):
    entries: list[XpHistoryEntry]
    next_cursor: str | None  # opaque to the client; pass back as-is to get the next page
