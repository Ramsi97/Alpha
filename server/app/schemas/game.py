from pydantic import BaseModel, ConfigDict


class GameOut(BaseModel):
    # validate_assignment=True: best_score is set via plain attribute
    # assignment after model_validate() (see app/api/v1/games.py) — no
    # active bug today (it's already a plain int), but consistent with
    # UserOut's fix for the same pattern and cheap insurance against one.
    model_config = ConfigDict(from_attributes=True, validate_assignment=True)

    slug: str
    version: str
    title: dict
    description: dict | None
    category: str
    thumbnail_url: str | None
    entry_url: str
    variants: list[str]
    max_score: int
    min_play_seconds: int
    xp_rate: float
    max_xp_per_run: int
    max_score_per_second: float
    status: str
    best_score: int | None = None
    is_favorite: bool = False
    recently_played: bool = False
    average_rating: float | None = None


class GameDetailOut(GameOut):
    license_code: str | None
    license_assets: str | None
    author: str | None
    source_url: str | None
