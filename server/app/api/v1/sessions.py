import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.core.db import get_db
from app.core.errors import ApiError
from app.core.rate_limit import rate_limit, rate_limit_per_ip
from app.models.game import Game
from app.models.session import GameSession
from app.models.user import User
from app.schemas.session import SessionCreateRequest, SessionCreateResponse, SessionFinishRequest, SessionFinishResponse
from app.services.sessions import create_session, finish_session

router = APIRouter()


@router.post(
    "/games/{slug}/sessions",
    response_model=SessionCreateResponse,
    dependencies=[
        rate_limit("session_start", limit=60, window_seconds=3600),  # plan section 8.2
        # Plan section 17: per-user AND per-IP. A bot farm running many
        # accounts behind one IP still gets throttled even though each
        # individual account is well within its own per-user limit.
        rate_limit_per_ip("session_start", limit=300, window_seconds=3600),
    ],
)
async def start_session(
    slug: str,
    body: SessionCreateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SessionCreateResponse:
    game = (await db.execute(select(Game).where(Game.slug == slug))).scalar_one_or_none()
    if game is None:
        raise ApiError(404, "not_found", f"No game with slug '{slug}'.")
    session, token = await create_session(db, user, game, body.variant)
    await db.commit()
    return SessionCreateResponse(session_id=session.id, token=token, seed=session.seed, variant=session.variant)


@router.post("/sessions/{session_id}/heartbeat")
async def heartbeat(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    session = (
        await db.execute(
            select(GameSession).where(GameSession.id == session_id, GameSession.user_id == user.id)
        )
    ).scalar_one_or_none()
    if session is None:
        raise ApiError(404, "not_found", "Session not found.")
    if session.status != "active":
        return {"active_seconds": session.active_seconds}

    now = datetime.now(UTC)
    last = session.last_heartbeat_at or session.started_at
    last = last if last.tzinfo else last.replace(tzinfo=UTC)
    elapsed = max(0, min(60, int((now - last).total_seconds())))  # cap a single gap at 60s
    session.active_seconds += elapsed
    session.last_heartbeat_at = now
    await db.commit()
    return {"active_seconds": session.active_seconds}


@router.post(
    "/sessions/{session_id}/finish",
    response_model=SessionFinishResponse,
    dependencies=[
        # Plan section 17: per-user AND per-IP (this route previously only
        # had the per-IP one — a single compromised/scripted account could
        # hammer finish with no per-user limit at all).
        rate_limit("session_finish", limit=120, window_seconds=3600),
        rate_limit_per_ip("session_finish", limit=300, window_seconds=3600),
    ],
)
async def finish(
    session_id: uuid.UUID,
    body: SessionFinishRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SessionFinishResponse:
    result = await finish_session(db, user, session_id, body.token, body.score, body.variant)
    return SessionFinishResponse(**result)
