"""Tournaments (plan section 13): a time-windowed competition on one
game+variant, scored either by best single run or the sum of the top N
runs, closed by a job that finalizes ranks and pays XP."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tournament import Tournament, TournamentEntry
from app.models.user import User
from app.models.xp_event import XpEvent
from app.services.notifications import queue_notification
from app.services.settings_store import get_setting
from app.services.xp import level_for_xp

DEFAULT_TOURNAMENT_RANK_XP = {"1": 300, "2": 200, "3": 100}


def _entry_score(tournament: Tournament, run_scores: list[int]) -> int:
    if tournament.rule == "sum_top_n":
        n = tournament.top_n or len(run_scores)
        return sum(sorted(run_scores, reverse=True)[:n])
    return max(run_scores) if run_scores else 0


async def get_or_create_entry(db: AsyncSession, tournament_id: int, user_id: int) -> TournamentEntry:
    entry = (
        await db.execute(
            select(TournamentEntry).where(
                TournamentEntry.tournament_id == tournament_id, TournamentEntry.user_id == user_id
            )
        )
    ).scalar_one_or_none()
    if entry is None:
        entry = TournamentEntry(tournament_id=tournament_id, user_id=user_id)
        db.add(entry)
        await db.flush()
    return entry


async def record_tournament_score(db: AsyncSession, user_id: int, game_id: int, variant: str | None, score: int) -> None:
    """Call after a valid, non-flagged run. Updates every currently-active
    tournament for this game+variant that the user has an entry in — a
    user who never called `join` simply doesn't participate, matching the
    plan's explicit `POST /tournaments/{id}/join` entry point."""
    now = datetime.now(UTC)
    tournaments = (
        await db.execute(
            select(Tournament).where(
                Tournament.game_id == game_id, Tournament.variant == variant,
                Tournament.status == "active", Tournament.starts_at <= now, Tournament.ends_at >= now,
            )
        )
    ).scalars().all()

    for tournament in tournaments:
        entry = (
            await db.execute(
                select(TournamentEntry).where(
                    TournamentEntry.tournament_id == tournament.id, TournamentEntry.user_id == user_id
                )
            )
        ).scalar_one_or_none()
        if entry is None:
            continue  # not joined — this run doesn't count

        entry.run_scores = [*entry.run_scores, score]
        entry.score = _entry_score(tournament, entry.run_scores)
        entry.updated_at = now

    if tournaments:
        await db.commit()


async def close_tournament(db: AsyncSession, tournament: Tournament) -> list[TournamentEntry]:
    entries = (
        await db.execute(
            select(TournamentEntry).where(TournamentEntry.tournament_id == tournament.id).order_by(TournamentEntry.score.desc())
        )
    ).scalars().all()

    rank_xp = await get_setting(db, "tournament_rank_xp", DEFAULT_TOURNAMENT_RANK_XP)

    for i, entry in enumerate(entries):
        rank = i + 1
        entry.rank = rank
        awarded = int(rank_xp.get(str(rank), 0))
        if awarded > 0:
            user = (await db.execute(select(User).where(User.id == entry.user_id))).scalar_one()
            db.add(XpEvent(
                user_id=user.id, source="tournament", amount=awarded,
                ref_type="tournament_rank", ref_id=str(tournament.id),
                idempotency_key=f"tournament_rank:{tournament.id}:{user.id}",
            ))
            user.total_xp += awarded
            user.level = level_for_xp(user.total_xp)
        queue_notification(db, entry.user_id, "tournament_end", {"rank": rank})

    tournament.status = "ended"
    await db.commit()
    return entries
