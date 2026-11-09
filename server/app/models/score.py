import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Score(Base):
    __tablename__ = "scores"
    __table_args__ = (
        Index("ix_scores_game_variant_value", "game_id", "variant", "value"),  # leaderboard rebuild (plan section 6)
        Index("ix_scores_user_game_created", "user_id", "game_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    game_id: Mapped[int] = mapped_column(Integer, ForeignKey("games.id"), nullable=False)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("game_sessions.id"), nullable=False, unique=True
    )
    variant: Mapped[str | None] = mapped_column(String)
    value: Mapped[int] = mapped_column(BigInteger, nullable=False)
    xp_awarded: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    flagged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Plan section 16/17: flagged runs are "held for review" — this tracks
    # whether an admin has acted on one yet (approve/reject), so the
    # review queue only shows runs nobody's looked at.
    admin_reviewed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
