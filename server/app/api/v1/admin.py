import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import require_admin
from app.core.db import get_db
from app.core.errors import ApiError
from app.core.telegram_client import TelegramClient, get_telegram_client
from app.models.game import Game
from app.models.score import Score
from app.models.setting import Setting
from app.models.sponsor import Sponsor
from app.models.task import Task, UserTask
from app.models.user import User
from app.models.xp_event import XpEvent
from app.schemas.admin import (
    AdminGamePatch,
    AdminScoreOut,
    AdminUserOut,
    AdminXpAdjustRequest,
    SettingOut,
    SettingPut,
)
from app.schemas.game import GameDetailOut
from app.schemas.sponsor import SponsorCreateRequest, SponsorOut, SponsorReportOut, SponsorTaskReport
from app.services.audit import log_action
from app.services.notifications import process_outbox
from app.services.seasons import active_season_id
from app.services.xp import level_for_xp

router = APIRouter(prefix="/admin")

VALID_STATUSES = {"pending", "active", "disabled"}


@router.get("/games", response_model=list[GameDetailOut])
async def admin_list_games(
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[GameDetailOut]:
    # Unlike the public GET /games, this returns every status (plan section
    # 16: admins review `pending` games before activating them).
    games = (await db.execute(select(Game).order_by(Game.slug))).scalars().all()
    return [GameDetailOut.model_validate(g) for g in games]


@router.patch("/games/{slug}", response_model=GameDetailOut)
async def admin_patch_game(
    slug: str,
    body: AdminGamePatch,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> GameDetailOut:
    game = (await db.execute(select(Game).where(Game.slug == slug))).scalar_one_or_none()
    if game is None:
        raise ApiError(404, "not_found", f"No game with slug '{slug}'.")

    if body.status is not None and body.status not in VALID_STATUSES:
        raise ApiError(400, "invalid_status", f"status must be one of {sorted(VALID_STATUSES)}.")

    changes = body.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(game, field, value)

    if changes:
        log_action(db, admin.id, "game.update", "game", slug, changes)
    await db.commit()
    return GameDetailOut.model_validate(game)


@router.get("/settings/{key}", response_model=SettingOut)
async def admin_get_setting(
    key: str,
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> SettingOut:
    row = (await db.execute(select(Setting).where(Setting.key == key))).scalar_one_or_none()
    if row is None:
        raise ApiError(404, "not_found", f"No setting '{key}'.")
    return SettingOut(key=row.key, value=row.value)


@router.put("/settings/{key}", response_model=SettingOut)
async def admin_put_setting(
    key: str,
    body: SettingPut,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> SettingOut:
    row = (await db.execute(select(Setting).where(Setting.key == key))).scalar_one_or_none()
    old_value = row.value if row else None
    if row is None:
        row = Setting(key=key, value=body.value)
        db.add(row)
    else:
        row.value = body.value

    log_action(db, admin.id, "setting.update", "setting", key, {"old": old_value, "new": body.value})
    await db.commit()
    return SettingOut(key=row.key, value=row.value)


# --- Users (plan section 16: "search, view XP ledger, ban/unban, XP adjustment") ---

@router.get("/users", response_model=list[AdminUserOut])
async def admin_search_users(
    search: str | None = Query(default=None),
    limit: int = Query(default=20, le=100),
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[AdminUserOut]:
    # Postgres' text columns can never legally contain a NUL byte (UTF-8
    # disallows it) — passing one through to ILIKE isn't a SQL injection
    # (the ORM still parameterizes it correctly), but asyncpg raises a
    # DBAPIError on the encode, which would otherwise surface as a 500
    # for a perfectly harmless "no such user" search.
    if search is not None:
        search = search.replace("\x00", "")

    query = select(User).order_by(User.id.desc()).limit(limit)
    if search:
        if search.isdigit():
            query = select(User).where(User.telegram_id == int(search)).limit(limit)
        else:
            query = select(User).where(User.username.ilike(f"%{search}%")).order_by(User.id.desc()).limit(limit)
    users = (await db.execute(query)).scalars().all()
    return [AdminUserOut.model_validate(u, from_attributes=True) for u in users]


async def _get_user_or_404(db: AsyncSession, user_id: int) -> User:
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        raise ApiError(404, "not_found", f"No user {user_id}.")
    return user


@router.post("/users/{user_id}/ban", response_model=AdminUserOut)
async def admin_ban_user(
    user_id: int, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
) -> AdminUserOut:
    user = await _get_user_or_404(db, user_id)
    user.is_banned = True
    log_action(db, admin.id, "user.ban", "user", str(user_id), {})
    await db.commit()
    return AdminUserOut.model_validate(user, from_attributes=True)


@router.post("/users/{user_id}/unban", response_model=AdminUserOut)
async def admin_unban_user(
    user_id: int, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
) -> AdminUserOut:
    user = await _get_user_or_404(db, user_id)
    user.is_banned = False
    log_action(db, admin.id, "user.unban", "user", str(user_id), {})
    await db.commit()
    return AdminUserOut.model_validate(user, from_attributes=True)


@router.post("/users/{user_id}/adjust-xp", response_model=AdminUserOut)
async def admin_adjust_xp(
    user_id: int,
    body: AdminXpAdjustRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminUserOut:
    """Plan section 9.3: admin XP changes are **ledger rows**, never a
    direct edit of users.total_xp — reversible, auditable, and the ledger
    stays the source of truth it's supposed to be."""
    user = await _get_user_or_404(db, user_id)
    key = body.idempotency_key or f"admin_adjust:{uuid.uuid4()}"
    db.add(XpEvent(
        user_id=user.id, source="admin", amount=body.amount,
        ref_type="admin_adjustment", ref_id=str(admin.id),
        idempotency_key=key,
        season_id=await active_season_id(db),
    ))
    user.total_xp += body.amount
    user.level = level_for_xp(user.total_xp)
    log_action(db, admin.id, "user.adjust_xp", "user", str(user_id), {"amount": body.amount, "reason": body.reason})
    await db.commit()
    return AdminUserOut.model_validate(user, from_attributes=True)


# --- Flagged runs (plan section 8.3/17: "hold for review", approve or reverse) ---

@router.get("/flagged-scores", response_model=list[AdminScoreOut])
async def admin_list_flagged_scores(
    limit: int = Query(default=50, le=200),
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[AdminScoreOut]:
    rows = (
        await db.execute(
            select(Score).where(Score.flagged == True, Score.admin_reviewed == False)  # noqa: E712
            .order_by(Score.created_at.desc()).limit(limit)
        )
    ).scalars().all()
    return [AdminScoreOut.model_validate(r, from_attributes=True) for r in rows]


@router.post("/flagged-scores/{score_id}/approve", response_model=AdminScoreOut)
async def admin_approve_flagged_score(
    score_id: int, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
) -> AdminScoreOut:
    """Admin confirms this was a legitimate run after all — awards the XP
    that was withheld. Uses a direct `score*xp_rate` formula capped by
    max_xp_per_run, not a full replay of compute_run_xp's diminishing-
    returns logic — the "runs today" context from the original moment is
    long gone by review time, so an exact replay isn't meaningful; this is
    a deliberately simpler approximation for the review-queue path only."""
    score = (await db.execute(select(Score).where(Score.id == score_id))).scalar_one_or_none()
    if score is None:
        raise ApiError(404, "not_found", f"No score {score_id}.")
    if score.admin_reviewed:
        raise ApiError(409, "already_reviewed", "This score was already reviewed.")

    game = (await db.execute(select(Game).where(Game.id == score.game_id))).scalar_one()
    user = await _get_user_or_404(db, score.user_id)

    xp = min(int(score.value * float(game.xp_rate)), game.max_xp_per_run)
    score.flagged = False
    score.admin_reviewed = True
    score.xp_awarded = xp
    if xp > 0:
        db.add(XpEvent(
            user_id=user.id, source="admin", amount=xp,
            ref_type="flagged_score_approval", ref_id=str(score.id),
            idempotency_key=f"flagged_approval:{score.id}",
            season_id=await active_season_id(db),
        ))
        user.total_xp += xp
        user.level = level_for_xp(user.total_xp)

    log_action(db, admin.id, "score.approve", "score", str(score_id), {"xp_awarded": xp})
    await db.commit()
    return AdminScoreOut.model_validate(score, from_attributes=True)


@router.post("/flagged-scores/{score_id}/reject", response_model=AdminScoreOut)
async def admin_reject_flagged_score(
    score_id: int, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
) -> AdminScoreOut:
    """Admin confirms this score really was implausible — stays flagged,
    no XP, just marked reviewed so it drops off the queue."""
    score = (await db.execute(select(Score).where(Score.id == score_id))).scalar_one_or_none()
    if score is None:
        raise ApiError(404, "not_found", f"No score {score_id}.")
    if score.admin_reviewed:
        raise ApiError(409, "already_reviewed", "This score was already reviewed.")

    score.admin_reviewed = True
    log_action(db, admin.id, "score.reject", "score", str(score_id), {})
    await db.commit()
    return AdminScoreOut.model_validate(score, from_attributes=True)


# --- Notifications (plan section 14.3) ---

@router.post("/notifications/process")
async def admin_process_notifications(
    rate_per_second: int = Query(default=25),
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    telegram_client: TelegramClient = Depends(get_telegram_client),
) -> dict:
    """Triggers one processing pass synchronously. The real deployment
    runs app/workers/notification_worker.py continuously instead; this
    endpoint exists for ops (manually clear a backlog) and for testing."""
    return await process_outbox(db, telegram_client, rate_per_second)


# --- Sponsors (plan section 16: "Tasks: ... sponsor association"; B5: "sponsored tasks and sponsor reports") ---

@router.get("/sponsors", response_model=list[SponsorOut])
async def admin_list_sponsors(
    _admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
) -> list[SponsorOut]:
    rows = (await db.execute(select(Sponsor).order_by(Sponsor.name))).scalars().all()
    return [SponsorOut.model_validate(s, from_attributes=True) for s in rows]


@router.post("/sponsors", response_model=SponsorOut)
async def admin_create_sponsor(
    body: SponsorCreateRequest, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
) -> SponsorOut:
    sponsor = Sponsor(name=body.name, contact_email=body.contact_email)
    db.add(sponsor)
    await db.flush()
    log_action(db, admin.id, "sponsor.create", "sponsor", str(sponsor.id), {"name": body.name})
    await db.commit()
    return SponsorOut.model_validate(sponsor, from_attributes=True)


@router.get("/sponsors/{sponsor_id}/report", response_model=SponsorReportOut)
async def admin_sponsor_report(
    sponsor_id: int, _admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
) -> SponsorReportOut:
    sponsor = (await db.execute(select(Sponsor).where(Sponsor.id == sponsor_id))).scalar_one_or_none()
    if sponsor is None:
        raise ApiError(404, "not_found", f"No sponsor {sponsor_id}.")

    tasks = (await db.execute(select(Task).where(Task.sponsor_id == sponsor_id))).scalars().all()
    task_reports = []
    for task in tasks:
        completions = (
            await db.execute(
                select(func.count()).select_from(UserTask).where(
                    UserTask.task_id == task.id, UserTask.status == "completed"
                )
            )
        ).scalar_one()
        # Ledger sum, not completions * xp_reward — correct even if
        # xp_reward changed after some completions were already awarded.
        xp_total = (
            await db.execute(
                select(func.coalesce(func.sum(XpEvent.amount), 0)).where(
                    XpEvent.ref_type == "task", XpEvent.ref_id == str(task.id)
                )
            )
        ).scalar_one()
        task_reports.append(SponsorTaskReport(task_id=task.id, title=task.title, completions=completions, xp_awarded_total=int(xp_total)))

    return SponsorReportOut(
        sponsor_id=sponsor.id, sponsor_name=sponsor.name, tasks=task_reports,
        total_completions=sum(t.completions for t in task_reports),
        total_xp_awarded=sum(t.xp_awarded_total for t in task_reports),
    )
