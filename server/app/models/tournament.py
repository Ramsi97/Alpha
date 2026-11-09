from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Tournament(Base):
    __tablename__ = "tournaments"
    __table_args__ = (
        CheckConstraint("rule IN ('best_score','sum_top_n')", name="tournaments_rule_check"),
        CheckConstraint("status IN ('upcoming','active','ended')", name="tournaments_status_check"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[dict] = mapped_column(JSONB, nullable=False)
    game_id: Mapped[int] = mapped_column(Integer, ForeignKey("games.id"), nullable=False)
    variant: Mapped[str | None] = mapped_column(String)
    rule: Mapped[str] = mapped_column(String, nullable=False, default="best_score")
    top_n: Mapped[int | None] = mapped_column(Integer)  # only used when rule == 'sum_top_n'
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="upcoming")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TournamentEntry(Base):
    __tablename__ = "tournament_entries"
    __table_args__ = (UniqueConstraint("tournament_id", "user_id", name="uq_tournament_entries_tournament_user"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tournament_id: Mapped[int] = mapped_column(Integer, ForeignKey("tournaments.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    score: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    # Every valid run's score during the window — needed to compute
    # 'sum_top_n' correctly (a later high score can bump an earlier one out
    # of the top N, which a running sum alone can't express). Unused for
    # 'best_score' tournaments beyond keeping a history.
    run_scores: Mapped[list[int]] = mapped_column(JSONB, nullable=False, default=list)
    rank: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
