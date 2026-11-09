"""Admin season management (plan section 16: "Seasons and tournaments:
create, schedule, finalize")."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import require_admin
from app.core.db import get_db
from app.core.errors import ApiError
from app.models.season import Season
from app.models.user import User
from app.schemas.season import SeasonCreateRequest, SeasonOut
from app.services.audit import log_action
from app.services.seasons import close_season

router = APIRouter(prefix="/admin")


@router.get("/seasons", response_model=list[SeasonOut])
async def admin_list_seasons(
    _admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
) -> list[SeasonOut]:
    seasons = (await db.execute(select(Season).order_by(Season.starts_at.desc()))).scalars().all()
    return [SeasonOut.model_validate(s, from_attributes=True) for s in seasons]


@router.post("/seasons", response_model=SeasonOut)
async def admin_create_season(
    body: SeasonCreateRequest, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
) -> SeasonOut:
    active = (await db.execute(select(Season).where(Season.status == "active"))).scalar_one_or_none()
    if active is not None:
        raise ApiError(409, "season_already_active", f"Season '{active.name}' is already active; finalize it first.")

    season = Season(name=body.name, starts_at=body.starts_at, ends_at=body.ends_at, status="active")
    db.add(season)
    await db.flush()
    log_action(db, admin.id, "season.create", "season", str(season.id), {"name": body.name})
    await db.commit()
    return SeasonOut.model_validate(season, from_attributes=True)


@router.post("/seasons/{season_id}/finalize", response_model=SeasonOut)
async def admin_finalize_season(
    season_id: int, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
) -> SeasonOut:
    """Manually runs the same logic as the scheduled end-of-season job
    (app/workers/end_season.py) for one season — useful for ops (end a
    season early) and for testing without waiting for `ends_at`."""
    season = (await db.execute(select(Season).where(Season.id == season_id))).scalar_one_or_none()
    if season is None:
        raise ApiError(404, "not_found", f"No season {season_id}.")
    if season.status == "ended":
        raise ApiError(409, "already_ended", "This season has already ended.")

    log_action(db, admin.id, "season.finalize", "season", str(season_id), {})
    await close_season(db, season)  # commits the audit row along with everything else
    return SeasonOut.model_validate(season, from_attributes=True)
