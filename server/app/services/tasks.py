"""Task engine (plan section 12).

verify_task() dispatches on task.type/verify_method. Three of the six
handler types are fully functional and tested end-to-end here:
play_game, daily_open, open_link/timed_claim, custom/manual.

join_channel has a real external dependency this pass can't fully close:
it needs a real Telegram bot that's an admin of the target channel —
unverifiable without one (see app/core/telegram_client.py). The handler
itself is implemented and unit-testable via FakeTelegramClient.

invite_friends counts *rewarded* referrals (plan section 12.4's
`referrals.status == 'rewarded'`, i.e. the referred friend actually played
a valid run — see app/services/referrals.py), not just signups, so a
referred friend who never plays doesn't satisfy this task.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.telegram_client import TelegramClient
from app.models.game import Game
from app.models.referral import Referral
from app.models.score import Score
from app.models.task import Task, UserTask
from app.models.user import User
from app.models.xp_event import XpEvent
from app.services.seasons import active_season_id
from app.services.xp import level_for_xp


def period_key_for(period: str, now: datetime) -> str:
    if period == "once":
        return "once"
    if period == "daily":
        return now.date().isoformat()
    if period == "weekly":
        iso = now.isocalendar()
        return f"{iso.year}-W{iso.week:02d}"
    raise ValueError(f"unknown task period '{period}'")


@dataclass
class VerifyResult:
    status: str  # 'started' (not yet met) | 'pending_review' | 'completed' | 'rejected'
    xp_awarded: int = 0


async def start_task(db: AsyncSession, user: User, task: Task) -> UserTask:
    now = datetime.now(UTC)
    period_key = period_key_for(task.period, now)
    existing = (
        await db.execute(
            select(UserTask).where(
                UserTask.user_id == user.id, UserTask.task_id == task.id, UserTask.period_key == period_key
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    user_task = UserTask(user_id=user.id, task_id=task.id, period_key=period_key, status="started")
    db.add(user_task)
    try:
        await db.flush()
        return user_task
    except IntegrityError:
        # Race: another request started this same (user, task, period) first.
        await db.rollback()
        return (
            await db.execute(
                select(UserTask).where(
                    UserTask.user_id == user.id, UserTask.task_id == task.id, UserTask.period_key == period_key
                )
            )
        ).scalar_one()


async def _global_completions(db: AsyncSession, task_id: int) -> int:
    return (
        await db.execute(
            select(func.count()).select_from(UserTask).where(UserTask.task_id == task_id, UserTask.status == "completed")
        )
    ).scalar_one()


async def _award_and_complete(db: AsyncSession, user: User, task: Task, user_task: UserTask) -> int:
    user_task.status = "completed"
    user_task.completed_at = datetime.now(UTC)
    xp = 0
    if task.xp_reward:
        db.add(XpEvent(
            user_id=user.id, source="task", amount=task.xp_reward,
            ref_type="task", ref_id=str(task.id),
            idempotency_key=f"task:{user.id}:{task.id}:{user_task.period_key}",
            season_id=await active_season_id(db),
        ))
        user.total_xp += task.xp_reward
        user.level = level_for_xp(user.total_xp)
        xp = task.xp_reward
    return xp


async def _check_play_game(db: AsyncSession, user: User, task: Task, user_task: UserTask) -> bool:
    payload = task.payload or {}
    game = (await db.execute(select(Game).where(Game.slug == payload.get("game_slug")))).scalar_one_or_none()
    if game is None:
        return False
    query = select(Score).where(
        Score.user_id == user.id, Score.game_id == game.id,
        Score.created_at >= user_task.started_at, Score.flagged == False,  # noqa: E712
    )
    min_score = payload.get("min_score")
    if min_score is not None:
        query = query.where(Score.value >= min_score)
    count = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
    return count >= payload.get("min_runs", 1)


async def _check_daily_open(user: User, now: datetime) -> bool:
    return user.last_checkin_date == now.date()


async def _check_timed_claim(task: Task, user_task: UserTask, now: datetime) -> bool:
    min_wait = (task.payload or {}).get("min_wait_seconds", 15)
    started_at = user_task.started_at if user_task.started_at.tzinfo else user_task.started_at.replace(tzinfo=UTC)
    return (now - started_at).total_seconds() >= min_wait


async def _check_invite_friends(db: AsyncSession, user: User, task: Task, user_task: UserTask) -> bool:
    min_referrals = (task.payload or {}).get("min_referrals", 1)
    count = (
        await db.execute(
            select(func.count()).select_from(Referral).where(
                Referral.referrer_id == user.id,
                Referral.status == "rewarded",
                Referral.rewarded_at >= user_task.started_at,
            )
        )
    ).scalar_one()
    return count >= min_referrals


async def _check_join_channel(telegram_client: TelegramClient, task: Task, user: User) -> bool:
    chat_id = (task.payload or {}).get("chat_id")
    if not chat_id:
        return False
    status = await telegram_client.get_chat_member_status(chat_id, user.telegram_id)
    return status in {"member", "administrator", "creator"}


async def verify_task(
    db: AsyncSession, user: User, task: Task, user_task: UserTask, telegram_client: TelegramClient | None = None
) -> VerifyResult:
    if user_task.status != "started":
        return VerifyResult(status=user_task.status)

    if task.max_total_completions is not None:
        if await _global_completions(db, task.id) >= task.max_total_completions:
            return VerifyResult(status="started")  # full; not this user's fault, just can't complete

    met = False
    if task.type == "play_game":
        met = await _check_play_game(db, user, task, user_task)
    elif task.type == "daily_open":
        met = await _check_daily_open(user, datetime.now(UTC))
    elif task.type in ("open_link", "share_story"):
        met = await _check_timed_claim(task, user_task, datetime.now(UTC))
    elif task.type == "invite_friends":
        met = await _check_invite_friends(db, user, task, user_task)
    elif task.type == "join_channel":
        if telegram_client is None:
            return VerifyResult(status="started")
        met = await _check_join_channel(telegram_client, task, user)
    elif task.type == "custom":
        if task.verify_method == "manual":
            user_task.status = "pending_review"
            await db.commit()
            return VerifyResult(status="pending_review")
        met = False

    if not met:
        return VerifyResult(status="started")

    xp = await _award_and_complete(db, user, task, user_task)
    await db.commit()
    return VerifyResult(status="completed", xp_awarded=xp)
