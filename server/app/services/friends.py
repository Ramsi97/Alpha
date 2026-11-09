"""Friends leaderboard (plan section 15): "Referral and challenge
connections" rather than a Redis set, since this graph is naturally small
per user and already lives in Postgres as the source of truth."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.challenge import Challenge, ChallengeBeat
from app.models.referral import Referral


async def friend_ids(db: AsyncSession, user_id: int) -> set[int]:
    referred_by_me = (
        await db.execute(select(Referral.referred_id).where(Referral.referrer_id == user_id))
    ).scalars().all()
    referred_me = (
        await db.execute(select(Referral.referrer_id).where(Referral.referred_id == user_id))
    ).scalars().all()

    my_challenge_ids = (
        await db.execute(select(Challenge.id).where(Challenge.challenger_id == user_id))
    ).scalars().all()
    beat_my_challenges = (
        await db.execute(select(ChallengeBeat.beater_id).where(ChallengeBeat.challenge_id.in_(my_challenge_ids)))
    ).scalars().all() if my_challenge_ids else []

    my_beat_challenge_ids = (
        await db.execute(select(ChallengeBeat.challenge_id).where(ChallengeBeat.beater_id == user_id))
    ).scalars().all()
    challenged_me = (
        await db.execute(select(Challenge.challenger_id).where(Challenge.id.in_(my_beat_challenge_ids)))
    ).scalars().all() if my_beat_challenge_ids else []

    return set(referred_by_me) | set(referred_me) | set(beat_my_challenges) | set(challenged_me)
