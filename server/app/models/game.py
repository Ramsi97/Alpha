from datetime import datetime

from sqlalchemy import ARRAY, BigInteger, CheckConstraint, DateTime, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Game(Base):
    __tablename__ = "games"
    __table_args__ = (CheckConstraint("status IN ('pending','active','disabled')", name="games_status_check"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    version: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[dict] = mapped_column(JSONB, nullable=False)
    description: Mapped[dict | None] = mapped_column(JSONB)
    category: Mapped[str] = mapped_column(String, nullable=False)
    thumbnail_url: Mapped[str | None] = mapped_column(String)
    entry_url: Mapped[str] = mapped_column(String, nullable=False)
    variants: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)

    max_score: Mapped[int] = mapped_column(BigInteger, nullable=False)
    min_play_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    max_score_per_second: Mapped[float] = mapped_column(Numeric, nullable=False)
    xp_rate: Mapped[float] = mapped_column(Numeric, nullable=False)
    max_xp_per_run: Mapped[int] = mapped_column(Integer, nullable=False)

    license_code: Mapped[str | None] = mapped_column(String)
    license_assets: Mapped[str | None] = mapped_column(String)
    author: Mapped[str | None] = mapped_column(String)
    source_url: Mapped[str | None] = mapped_column(String)
    size_kb: Mapped[int | None] = mapped_column(Integer)

    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    trending_score: Mapped[float] = mapped_column(Numeric, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
