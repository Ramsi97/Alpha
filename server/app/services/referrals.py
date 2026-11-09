"""Referrals (plan section 12.4).

Activation happens on the referred user's first-ever *valid* (non-flagged)
scored run — not just opening the app, per the plan's explicit wording.
Abuse limits (daily/total cap) apply only to the referrer's reward; the
referred user's welcome bonus is unconditional, same as real Wordle-style
onboarding bonuses elsewhere in this plan.
"""

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.referral import Referral
from app.models.score import Score
from app.models.user import User
from app.models.xp_event import XpEvent
from app.services.notifications import queue_notification
from app.services.seasons import active_season_id
from app.services.settings_store import get_setting
from app.services.xp import level_for_xp

DEFAULT_REFERRAL_XP_REFERRER = 50
DEFAULT_REFERRAL_XP_REFERRED = 25
DEFAULT_REFERRAL_DAILY_CAP = 5
DEFAULT_REFERRAL_TOTAL_CAP = 100


def create_pending_referral(db: AsyncSession, referrer_id: int, referred_id: int) -> None:
    db.add(Referral(referrer_id=referrer_id, referred_id=referred_id, status="pending"))


async def activate_referral_if_eligible(db: AsyncSession, user: User) -> Referral | None:
    """Call right after a user's run has been confirmed as their first-ever
    valid (non-flagged) score. Returns the activated Referral row, or None
    if there was nothing to activate (no pending referral, or this wasn't
    actually their first valid run — e.g. called again on a later run)."""
    referral = (
        await db.execute(select(Referral).where(Referral.referred_id == user.id, Referral.status == "pending"))
    ).scalar_one_or_none()
    if referral is None:
        return None

    valid_run_count = (
        await db.execute(
            select(func.count()).select_from(Score).where(Score.user_id == user.id, Score.flagged == False)  # noqa: E712
        )
    ).scalar_one()
    if valid_run_count != 1:
        return None  # not their first valid run

    referrer = (await db.execute(select(User).where(User.id == referral.referrer_id))).scalar_one()

    referred_xp = await get_setting(db, "referral_xp_referred", DEFAULT_REFERRAL_XP_REFERRED)
    referrer_xp = await get_setting(db, "referral_xp_referrer", DEFAULT_REFERRAL_XP_REFERRER)
    daily_cap = await get_setting(db, "referral_daily_cap", DEFAULT_REFERRAL_DAILY_CAP)
    total_cap = await get_setting(db, "referral_total_cap", DEFAULT_REFERRAL_TOTAL_CAP)

    # Count the referrer's *existing* rewarded referrals before touching
    # this one's status — deliberately queried before any mutation below,
    # so autoflush can't make this referral count itself in its own cap check.
    today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    total_rewarded_so_far = (
        await db.execute(
            select(func.count()).select_from(Referral).where(
                Referral.referrer_id == referrer.id, Referral.status == "rewarded"
            )
        )
    ).scalar_one()
    today_rewarded_so_far = (
        await db.execute(
            select(func.count()).select_from(Referral).where(
                Referral.referrer_id == referrer.id, Referral.status == "rewarded", Referral.rewarded_at >= today_start
            )
        )
    ).scalar_one()
    referrer_under_cap = total_rewarded_so_far < total_cap and today_rewarded_so_far < daily_cap

    referral.status = "rewarded"
    referral.rewarded_at = datetime.now(UTC)
    season_id = await active_season_id(db)

    # Referred side: unconditional welcome bonus.
    db.add(XpEvent(
        user_id=user.id, source="referral", amount=referred_xp,
        ref_type="referral", ref_id=str(referral.id),
        idempotency_key=f"referral:{referral.id}:referred",
        season_id=season_id,
    ))
    user.total_xp += referred_xp
    user.level = level_for_xp(user.total_xp)

    # Referrer side: capped (plan section 12.4 abuse limits). Referral
    # still activates (the referred user's bonus always lands) even if the
    # referrer is over cap — only the referrer's own reward is withheld.
    if referrer_under_cap:
        db.add(XpEvent(
            user_id=referrer.id, source="referral", amount=referrer_xp,
            ref_type="referral", ref_id=str(referral.id),
            idempotency_key=f"referral:{referral.id}:referrer",
            season_id=season_id,
        ))
        referrer.total_xp += referrer_xp
        referrer.level = level_for_xp(referrer.total_xp)
        queue_notification(db, referrer.id, "friend_joined", {})

    return referral
