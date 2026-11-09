from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user, require_admin
from app.core.db import get_db
from app.core.errors import ApiError
from app.core.rate_limit import rate_limit, rate_limit_per_ip
from app.core.telegram_client import TelegramClient, get_telegram_client
from app.models.task import Task, UserTask
from app.models.user import User
from app.models.xp_event import XpEvent
from app.schemas.task import AdminTaskCreate, AdminTaskOut, AdminTaskPatch, AdminUserTaskOut, TaskOut, VerifyResultOut
from app.services.audit import log_action
from app.services.seasons import active_season_id
from app.services.tasks import period_key_for, start_task, verify_task
from app.services.xp import level_for_xp

router = APIRouter()


@router.get("/tasks", response_model=list[TaskOut])
async def list_tasks(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> list[TaskOut]:
    now = datetime.now(UTC)
    tasks = (
        await db.execute(
            select(Task).where(
                Task.active == True,  # noqa: E712
                (Task.starts_at.is_(None)) | (Task.starts_at <= now),
                (Task.ends_at.is_(None)) | (Task.ends_at >= now),
            )
        )
    ).scalars().all()

    out = []
    for task in tasks:
        period_key = period_key_for(task.period, now)
        user_task = (
            await db.execute(
                select(UserTask).where(
                    UserTask.user_id == user.id, UserTask.task_id == task.id, UserTask.period_key == period_key
                )
            )
        ).scalar_one_or_none()
        out.append(TaskOut(
            id=task.id, type=task.type, title=task.title, description=task.description,
            xp_reward=task.xp_reward, period=task.period, verify_method=task.verify_method,
            status=user_task.status if user_task else None,
        ))
    return out


async def _get_active_task(db: AsyncSession, task_id: int) -> Task:
    task = (await db.execute(select(Task).where(Task.id == task_id, Task.active == True))).scalar_one_or_none()  # noqa: E712
    if task is None:
        raise ApiError(404, "not_found", f"No active task {task_id}.")
    return task


@router.post(
    "/tasks/{task_id}/start",
    dependencies=[
        rate_limit("task_start", limit=120, window_seconds=3600),
        rate_limit_per_ip("task_start", limit=600, window_seconds=3600),
    ],
)
async def task_start(
    task_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    task = await _get_active_task(db, task_id)
    user_task = await start_task(db, user, task)
    await db.commit()
    return {"task_id": task.id, "period_key": user_task.period_key, "status": user_task.status, "payload": task.payload}


@router.post(
    "/tasks/{task_id}/verify",
    response_model=VerifyResultOut,
    dependencies=[
        # Plan section 17 explicitly names "task verifies" among the
        # routes needing per-user AND per-IP limits — this route had
        # neither before.
        rate_limit("task_verify", limit=120, window_seconds=3600),
        rate_limit_per_ip("task_verify", limit=600, window_seconds=3600),
    ],
)
async def task_verify(
    task_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    telegram_client: TelegramClient = Depends(get_telegram_client),
) -> VerifyResultOut:
    task = await _get_active_task(db, task_id)
    now = datetime.now(UTC)
    period_key = period_key_for(task.period, now)
    user_task = (
        await db.execute(
            select(UserTask).where(
                UserTask.user_id == user.id, UserTask.task_id == task.id, UserTask.period_key == period_key
            )
        )
    ).scalar_one_or_none()
    if user_task is None:
        raise ApiError(400, "not_started", "Call /tasks/{id}/start first.")

    result = await verify_task(db, user, task, user_task, telegram_client=telegram_client)
    return VerifyResultOut(status=result.status, xp_awarded=result.xp_awarded)


# --- Admin: task CRUD + manual review queue (plan section 16) ---

@router.get("/admin/tasks", response_model=list[AdminTaskOut])
async def admin_list_tasks(_admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)) -> list[AdminTaskOut]:
    tasks = (await db.execute(select(Task).order_by(Task.id))).scalars().all()
    return [AdminTaskOut.model_validate(t, from_attributes=True) for t in tasks]


@router.post("/admin/tasks", response_model=AdminTaskOut)
async def admin_create_task(
    body: AdminTaskCreate, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
) -> AdminTaskOut:
    task = Task(**body.model_dump())
    db.add(task)
    await db.flush()
    log_action(db, admin.id, "task.create", "task", str(task.id), body.model_dump(mode="json"))
    await db.commit()
    return AdminTaskOut.model_validate(task, from_attributes=True)


@router.patch("/admin/tasks/{task_id}", response_model=AdminTaskOut)
async def admin_patch_task(
    task_id: int, body: AdminTaskPatch, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
) -> AdminTaskOut:
    task = (await db.execute(select(Task).where(Task.id == task_id))).scalar_one_or_none()
    if task is None:
        raise ApiError(404, "not_found", f"No task {task_id}.")
    changes = body.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(task, field, value)
    if changes:
        log_action(db, admin.id, "task.update", "task", str(task_id), changes)
    await db.commit()
    return AdminTaskOut.model_validate(task, from_attributes=True)


@router.get("/admin/tasks/review-queue", response_model=list[AdminUserTaskOut])
async def admin_task_review_queue(
    _admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
) -> list[AdminUserTaskOut]:
    rows = (
        await db.execute(select(UserTask).where(UserTask.status == "pending_review").order_by(UserTask.started_at))
    ).scalars().all()
    return [AdminUserTaskOut.model_validate(r, from_attributes=True) for r in rows]


async def _get_pending_user_task(db: AsyncSession, user_task_id: int) -> UserTask:
    ut = (await db.execute(select(UserTask).where(UserTask.id == user_task_id))).scalar_one_or_none()
    if ut is None:
        raise ApiError(404, "not_found", f"No user_task {user_task_id}.")
    if ut.status != "pending_review":
        raise ApiError(409, "not_pending", f"user_task {user_task_id} is '{ut.status}', not pending_review.")
    return ut


@router.post("/admin/user-tasks/{user_task_id}/approve", response_model=AdminUserTaskOut)
async def admin_approve_user_task(
    user_task_id: int, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
) -> AdminUserTaskOut:
    user_task = await _get_pending_user_task(db, user_task_id)
    task = (await db.execute(select(Task).where(Task.id == user_task.task_id))).scalar_one()
    user = (await db.execute(select(User).where(User.id == user_task.user_id))).scalar_one()

    user_task.status = "completed"
    user_task.completed_at = datetime.now(UTC)
    if task.xp_reward:
        db.add(XpEvent(
            user_id=user.id, source="task", amount=task.xp_reward,
            ref_type="task", ref_id=str(task.id),
            idempotency_key=f"task:{user.id}:{task.id}:{user_task.period_key}",
            season_id=await active_season_id(db),
        ))
        user.total_xp += task.xp_reward
        user.level = level_for_xp(user.total_xp)

    log_action(db, admin.id, "task.approve_review", "user_task", str(user_task_id), {})
    await db.commit()
    return AdminUserTaskOut.model_validate(user_task, from_attributes=True)


@router.post("/admin/user-tasks/{user_task_id}/reject", response_model=AdminUserTaskOut)
async def admin_reject_user_task(
    user_task_id: int, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
) -> AdminUserTaskOut:
    user_task = await _get_pending_user_task(db, user_task_id)
    user_task.status = "rejected"
    log_action(db, admin.id, "task.reject_review", "user_task", str(user_task_id), {})
    await db.commit()
    return AdminUserTaskOut.model_validate(user_task, from_attributes=True)
