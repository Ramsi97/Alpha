from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class XpEvent(Base):
    __tablename__ = "xp_events"
    __table_args__ = (
        Index("ix_xp_events_user_created", "user_id", "created_at"),  # plan section 6
        Index("ix_xp_events_season_user", "season_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    ref_type: Mapped[str | None] = mapped_column(String)
    ref_id: Mapped[str | None] = mapped_column(String)
    season_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("seasons.id"))
    idempotency_key: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
