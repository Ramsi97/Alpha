from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Challenge(Base):
    __tablename__ = "challenges"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    challenger_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    game_id: Mapped[int] = mapped_column(Integer, ForeignKey("games.id"), nullable=False)
    variant: Mapped[str | None] = mapped_column(String)
    score_to_beat: Mapped[int] = mapped_column(BigInteger, nullable=False)
    token: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ChallengeBeat(Base):
    """One row per (challenge, beater) — a friend who beat the target
    score. Plural beats per challenge are allowed (share it widely); the
    unique constraint just stops the same beater re-triggering the
    challenger's reward on a second run."""

    __tablename__ = "challenge_beats"
    __table_args__ = (UniqueConstraint("challenge_id", "beater_id", name="uq_challenge_beats_challenge_beater"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    challenge_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("challenges.id"), nullable=False)
    beater_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    beaten_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
