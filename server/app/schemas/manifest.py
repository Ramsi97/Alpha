from pydantic import BaseModel, Field


class ManifestScore(BaseModel):
    mode: str
    higher_is_better: bool
    max_score: float = Field(ge=0)
    min_play_seconds: float = Field(ge=0)
    max_score_per_second: float = Field(ge=0)


class ManifestXp(BaseModel):
    rate: float = Field(ge=0)
    max_per_run: float = Field(ge=0)


class ManifestLicense(BaseModel):
    code: str
    assets: str
    author: str
    source_url: str


class GameManifest(BaseModel):
    """Mirrors games/_tools/game-manifest.schema.json (plan section 5.3) —
    the backend's own validation pass on top of (not instead of) the
    Node validator the games repo already runs."""

    slug: str
    version: str
    title: dict[str, str]
    description: dict[str, str]
    category: str
    thumbnail: str
    entry: str
    orientation: str
    variants: list[str] = []
    score: ManifestScore
    xp: ManifestXp
    license: ManifestLicense
    size_kb: float = Field(ge=0)
    status: str
