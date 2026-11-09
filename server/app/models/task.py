from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint("period IN ('once','daily','weekly')", name="tasks_period_check"),
        CheckConstraint(
            "verify_method IN ('auto','timed_claim','manual')", name="tasks_verify_method_check"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(String, nullable=False)  # join_channel, play_game, invite_friends, open_link, daily_open, custom
    title: Mapped[dict] = mapped_column(JSONB, nullable=False)
    description: Mapped[dict | None] = mapped_column(JSONB)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    xp_reward: Mapped[int] = mapped_column(Integer, nullable=False)
    period: Mapped[str] = mapped_column(String, nullable=False, default="once")
    verify_method: Mapped[str] = mapped_column(String, nullable=False)
    sponsor_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("sponsors.id"))
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    max_total_completions: Mapped[int | None] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class UserTask(Base):
    __tablename__ = "user_tasks"
    __table_args__ = (
        CheckConstraint(
            "status IN ('started','pending_review','completed','rejected')", name="user_tasks_status_check"
        ),
        UniqueConstraint("user_id", "task_id", "period_key", name="uq_user_tasks_user_task_period"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    task_id: Mapped[int] = mapped_column(Integer, ForeignKey("tasks.id"), nullable=False)
    period_key: Mapped[str] = mapped_column(String, nullable=False)  # 'once' | '2026-11-05' | '2026-W45'
    status: Mapped[str] = mapped_column(String, nullable=False, default="started")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
