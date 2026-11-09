from datetime import datetime

from pydantic import BaseModel


class SponsorOut(BaseModel):
    id: int
    name: str
    contact_email: str | None
    created_at: datetime


class SponsorCreateRequest(BaseModel):
    name: str
    contact_email: str | None = None


class SponsorTaskReport(BaseModel):
    task_id: int
    title: dict
    completions: int
    xp_awarded_total: int


class SponsorReportOut(BaseModel):
    sponsor_id: int
    sponsor_name: str
    tasks: list[SponsorTaskReport]
    total_completions: int
    total_xp_awarded: int
