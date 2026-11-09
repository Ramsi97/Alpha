"""Admin analytics (plan section 21/B5: "Analytics queries and dashboards
(DAU, retention, runs per game, task completion, referral conversion)").

Plain SQL aggregates behind one admin endpoint — no dashboard UI, same
"API only, no frontend" precedent as the rest of the admin surface in this
backend-only pass (see server/README.md)."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import require_admin
from app.core.db import get_db
from app.models.game import Game
from app.models.referral import Referral
from app.models.session import GameSession
from app.models.task import UserTask
from app.models.user import User
from app.schemas.analytics import AnalyticsOverviewOut, GameRunsRow

router = APIRouter(prefix="/admin")


@router.get("/analytics/overview", response_model=AnalyticsOverviewOut)
async def admin_analytics_overview(
    _admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
) -> AnalyticsOverviewOut:
    now = datetime.now(UTC)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_start = today_start - timedelta(days=1)
    seven_days_ago = now - timedelta(days=7)

    dau = (
        await db.execute(
            select(func.count(func.distinct(GameSession.user_id))).where(GameSession.started_at >= today_start)
        )
    ).scalar_one()

    cohort_ids = (
        await db.execute(
            select(User.id).where(User.created_at >= yesterday_start, User.created_at < today_start)
        )
    ).scalars().all()
    day1_retention = None
    if cohort_ids:
        retained = (
            await db.execute(
                select(func.count(func.distinct(GameSession.user_id))).where(
                    GameSession.user_id.in_(cohort_ids), GameSession.started_at >= today_start
                )
            )
        ).scalar_one()
        day1_retention = retained / len(cohort_ids)

    runs_rows = (
        await db.execute(
            select(Game.slug, func.count(GameSession.id))
            .join(GameSession, GameSession.game_id == Game.id)
            .where(GameSession.status == "finished", GameSession.finished_at >= seven_days_ago)
            .group_by(Game.slug)
            .order_by(func.count(GameSession.id).desc())
        )
    ).all()
    runs_per_game = [GameRunsRow(game_slug=slug, runs_last_7_days=count) for slug, count in runs_rows]

    total_tasks_started = (await db.execute(select(func.count()).select_from(UserTask))).scalar_one()
    task_completion_rate = None
    if total_tasks_started:
        completed = (
            await db.execute(select(func.count()).select_from(UserTask).where(UserTask.status == "completed"))
        ).scalar_one()
        task_completion_rate = completed / total_tasks_started

    total_referrals = (await db.execute(select(func.count()).select_from(Referral))).scalar_one()
    referral_conversion = None
    if total_referrals:
        rewarded = (
            await db.execute(select(func.count()).select_from(Referral).where(Referral.status == "rewarded"))
        ).scalar_one()
        referral_conversion = rewarded / total_referrals

    return AnalyticsOverviewOut(
        dau=dau, day1_retention=day1_retention, runs_per_game=runs_per_game,
        task_completion_rate=task_completion_rate, referral_conversion=referral_conversion,
    )
