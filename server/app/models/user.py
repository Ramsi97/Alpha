from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, Date, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    username: Mapped[str | None] = mapped_column(String)
    first_name: Mapped[str | None] = mapped_column(String)
    last_name: Mapped[str | None] = mapped_column(String)
    photo_url: Mapped[str | None] = mapped_column(String)
    language: Mapped[str] = mapped_column(String, nullable=False, default="en")

    total_xp: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    streak_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    streak_freezes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_checkin_date: Mapped[date | None] = mapped_column(Date)

    referral_code: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    referred_by: Mapped[int | None] = mapped_column(BigInteger)

    notifications_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    bot_blocked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_banned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Plan section 18: "Provide a simple data-deletion path." Set by
    # DELETE /me (app/services/account_deletion.py), which also nulls the
    # PII fields above. The row itself and every FK pointing at it
    # (scores, xp_events, ...) stay — same "ledger is never deleted"
    # principle already used for admin XP reversals — only re-identifying
    # personal data is removed. Re-authenticating via Telegram afterward
    # clears this (see app/services/auth.py:get_or_create_user) since that
    # is itself fresh, renewed consent.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
