"""Tournaments (plan sections 13, 15, 16): public list/join/detail plus
admin create/close."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user, require_admin
from app.core.db import get_db
from app.core.errors import ApiError
from app.models.game import Game
from app.models.tournament import Tournament, TournamentEntry
from app.models.user import User
from app.schemas.tournament import TournamentCreateRequest, TournamentEntryOut, TournamentOut
from app.services.audit import log_action
from app.services.tournaments import close_tournament, get_or_create_entry

router = APIRouter()
admin_router = APIRouter(prefix="/admin")


async def _to_out(db: AsyncSession, tournament: Tournament, user: User) -> TournamentOut:
    game = (await db.execute(select(Game).where(Game.id == tournament.game_id))).scalar_one()
    entry = (
        await db.execute(
            select(TournamentEntry).where(
                TournamentEntry.tournament_id == tournament.id, TournamentEntry.user_id == user.id
            )
        )
    ).scalar_one_or_none()
    return TournamentOut(
        id=tournament.id, title=tournament.title, game_slug=game.slug, variant=tournament.variant,
        rule=tournament.rule, top_n=tournament.top_n, starts_at=tournament.starts_at, ends_at=tournament.ends_at,
        status=tournament.status, my_score=entry.score if entry else None, my_rank=entry.rank if entry else None,
    )


@router.get("/tournaments", response_model=list[TournamentOut])
async def list_tournaments(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[TournamentOut]:
    tournaments = (
        await db.execute(select(Tournament).where(Tournament.status != "ended").order_by(Tournament.starts_at))
    ).scalars().all()
    return [await _to_out(db, t, user) for t in tournaments]


@router.get("/tournaments/{tournament_id}", response_model=TournamentOut)
async def get_tournament(
    tournament_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> TournamentOut:
    tournament = (await db.execute(select(Tournament).where(Tournament.id == tournament_id))).scalar_one_or_none()
    if tournament is None:
        raise ApiError(404, "not_found", f"No tournament {tournament_id}.")
    return await _to_out(db, tournament, user)


@router.get("/tournaments/{tournament_id}/entries", response_model=list[TournamentEntryOut])
async def get_tournament_entries(
    tournament_id: int, _user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[TournamentEntryOut]:
    rows = (
        await db.execute(
            select(TournamentEntry, User)
            .join(User, User.id == TournamentEntry.user_id)
            .where(TournamentEntry.tournament_id == tournament_id)
            .order_by(TournamentEntry.score.desc())
            .limit(200)
        )
    ).all()
    return [
        TournamentEntryOut(rank=entry.rank, user_id=u.id, username=u.username, first_name=u.first_name, score=entry.score)
        for entry, u in rows
    ]


@router.post("/tournaments/{tournament_id}/join", response_model=TournamentOut)
async def join_tournament(
    tournament_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> TournamentOut:
    tournament = (await db.execute(select(Tournament).where(Tournament.id == tournament_id))).scalar_one_or_none()
    if tournament is None:
        raise ApiError(404, "not_found", f"No tournament {tournament_id}.")
    if tournament.status == "ended":
        raise ApiError(409, "tournament_ended", "This tournament has already ended.")

    await get_or_create_entry(db, tournament_id, user.id)
    await db.commit()
    return await _to_out(db, tournament, user)


@admin_router.post("/tournaments", response_model=TournamentOut)
async def admin_create_tournament(
    body: TournamentCreateRequest, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
) -> TournamentOut:
    game = (await db.execute(select(Game).where(Game.slug == body.game_slug))).scalar_one_or_none()
    if game is None:
        raise ApiError(404, "not_found", f"No game with slug '{body.game_slug}'.")
    if body.rule not in ("best_score", "sum_top_n"):
        raise ApiError(400, "invalid_rule", "rule must be 'best_score' or 'sum_top_n'.")

    tournament = Tournament(
        title=body.title, game_id=game.id, variant=body.variant, rule=body.rule, top_n=body.top_n,
        starts_at=body.starts_at, ends_at=body.ends_at, status="active",
    )
    db.add(tournament)
    await db.flush()
    log_action(db, admin.id, "tournament.create", "tournament", str(tournament.id), {"game_slug": body.game_slug})
    await db.commit()
    return await _to_out(db, tournament, admin)


@admin_router.post("/tournaments/{tournament_id}/close", response_model=list[TournamentEntryOut])
async def admin_close_tournament(
    tournament_id: int, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
) -> list[TournamentEntryOut]:
    """Manually runs the same logic as the scheduled closing job
    (app/workers/close_tournaments.py) — useful for ops and for testing."""
    tournament = (await db.execute(select(Tournament).where(Tournament.id == tournament_id))).scalar_one_or_none()
    if tournament is None:
        raise ApiError(404, "not_found", f"No tournament {tournament_id}.")
    if tournament.status == "ended":
        raise ApiError(409, "already_ended", "This tournament has already ended.")

    log_action(db, admin.id, "tournament.close", "tournament", str(tournament_id), {})
    entries = await close_tournament(db, tournament)  # commits the audit row along with everything else

    rows = (
        await db.execute(select(User).where(User.id.in_([e.user_id for e in entries])))
    ).scalars().all() if entries else []
    users_by_id = {u.id: u for u in rows}
    return [
        TournamentEntryOut(
            rank=e.rank, user_id=e.user_id,
            username=users_by_id[e.user_id].username if e.user_id in users_by_id else None,
            first_name=users_by_id[e.user_id].first_name if e.user_id in users_by_id else None,
            score=e.score,
        )
        for e in entries
    ]
