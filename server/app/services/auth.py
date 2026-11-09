import secrets
import string

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.admin import AdminUser
from app.models.user import User
from app.services.referrals import create_pending_referral

_ALPHABET = string.ascii_lowercase + string.digits


def _random_referral_code(length: int = 8) -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(length))


async def get_or_create_user(db: AsyncSession, telegram_user: dict, start_param: str | None) -> User:
    telegram_id = telegram_user["id"]
    existing = (await db.execute(select(User).where(User.telegram_id == telegram_id))).scalar_one_or_none()
    if existing is not None:
        existing.username = telegram_user.get("username") or existing.username
        existing.first_name = telegram_user.get("first_name") or existing.first_name
        existing.last_name = telegram_user.get("last_name") or existing.last_name
        existing.photo_url = telegram_user.get("photo_url") or existing.photo_url
        existing.language = telegram_user.get("language_code") or existing.language
        if existing.deleted_at is not None:
            # Fresh, real initData from Telegram is itself renewed consent
            # — undoes a prior DELETE /me rather than leaving the account
            # permanently locked out just because it was once deleted.
            existing.deleted_at = None
            existing.notifications_enabled = True
        return existing

    referred_by_id: int | None = None
    # Self-referral is structurally impossible here: the new user's own
    # referral_code doesn't exist yet at this point, so they can't name it
    # in start_param (plan section 12.4 "no self-referral").
    if start_param and start_param.startswith("r_"):
        code = start_param[2:]
        referrer = (await db.execute(select(User).where(User.referral_code == code))).scalar_one_or_none()
        if referrer is not None:
            referred_by_id = referrer.id

    for _ in range(5):  # retry on the astronomically unlikely referral_code collision
        user = User(
            telegram_id=telegram_id,
            username=telegram_user.get("username"),
            first_name=telegram_user.get("first_name"),
            last_name=telegram_user.get("last_name"),
            photo_url=telegram_user.get("photo_url"),
            language=telegram_user.get("language_code") or "en",
            referral_code=_random_referral_code(),
            referred_by=referred_by_id,
        )
        db.add(user)
        try:
            await db.flush()
            if referred_by_id is not None:
                create_pending_referral(db, referred_by_id, user.id)
                await db.flush()
            return user
        except IntegrityError:
            await db.rollback()
            # Could be a referral_code collision (retry with a fresh one) or a
            # concurrent request that already created this same telegram_id
            # (just return that row instead of retrying forever).
            concurrent = (
                await db.execute(select(User).where(User.telegram_id == telegram_id))
            ).scalar_one_or_none()
            if concurrent is not None:
                return concurrent
    raise RuntimeError("could not generate a unique referral_code after 5 attempts")


async def ensure_admin_bootstrap(db: AsyncSession, user: User) -> None:
    """If this user's telegram_id is in ADMIN_TELEGRAM_IDS (plan section 4),
    make sure they have an admin_users row. Self-healing on every login
    rather than a one-time migration step, so adding a new admin is just an
    env var change — no DB script to remember to run. Cheap: one indexed
    lookup on a tiny table, every auth call."""
    if user.telegram_id not in settings.admin_telegram_id_list:
        return
    existing = (await db.execute(select(AdminUser).where(AdminUser.user_id == user.id))).scalar_one_or_none()
    if existing is None:
        db.add(AdminUser(user_id=user.id, role="admin"))
        await db.commit()
