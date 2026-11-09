from pydantic import BaseModel


class GameRunsRow(BaseModel):
    game_slug: str
    runs_last_7_days: int


class AnalyticsOverviewOut(BaseModel):
    dau: int
    day1_retention: float | None  # None if yesterday's signup cohort is empty
    runs_per_game: list[GameRunsRow]
    task_completion_rate: float | None  # None if no tasks have ever been started
    referral_conversion: float | None  # None if no referrals exist yet
