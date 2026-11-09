"""Integration tests for seasons (plan section 13): season creation,
season_id stamped on XP ledger rows, the season leaderboard, and the
end-of-season finalize job (freeze results, pay rank XP, start the next
season)."""

import hashlib
import hmac
import json
import time
import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from sqlalchemy import select, update as sa_update

from app.core.config import settings
from app.models.game import Game
from app.models.season import Season, SeasonResult
from app.models.session import GameSession
from app.models.user import User
from app.models.xp_event import XpEvent

GAME_2048 = dict(
    slug="2048", version="1.0.0", title={"en": "2048"}, description={"en": "d"},
    category="number-puzzle", thumbnail_url="t.svg", entry_url="http://x/2048/index.html",
    variants=[], max_score=500000, min_play_seconds=20, max_score_per_second=1000,
    xp_rate=0.01, max_xp_per_run=300, license_code="MIT", license_assets="none",
    author="a", source_url="http://x", size_kb=136, status="active",
)


def make_init_data(telegram_id: int) -> str:
    user = json.dumps({"id": telegram_id, "first_name": f"P{telegram_id}", "language_code": "en"})
    pairs = {"auth_date": str(int(time.time())), "user": user}
    data_check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", settings.bot_token.encode(), hashlib.sha256).digest()
    pairs["hash"] = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    return urlencode(pairs)


async def _auth(client, telegram_id: int) -> dict:
    r = await client.post("/api/v1/auth/telegram", json={"init_data": make_init_data(telegram_id)})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _play_and_finish(client, db_session, headers, score: int) -> dict:
    r = await client.post("/api/v1/games/2048/sessions", json={}, headers=headers)
    sess = r.json()
    past = datetime.now(UTC) - timedelta(seconds=30)
    await db_session.execute(
        sa_update(GameSession).where(GameSession.id == uuid.UUID(sess["session_id"])).values(started_at=past)
    )
    await db_session.commit()
    r2 = await client.post(
        f"/api/v1/sessions/{sess['session_id']}/finish",
        json={"token": sess["token"], "score": score}, headers=headers,
    )
    return r2.json()


async def test_admin_create_season_and_duplicate_rejected(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "admin_telegram_ids", "9501")
    headers = await _auth(client, 9501)

    now = datetime.now(UTC)
    r = await client.post(
        "/api/v1/admin/seasons",
        json={"name": "Season 1", "starts_at": now.isoformat(), "ends_at": (now + timedelta(days=30)).isoformat()},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "active"

    r2 = await client.post(
        "/api/v1/admin/seasons",
        json={"name": "Season 2", "starts_at": now.isoformat(), "ends_at": (now + timedelta(days=30)).isoformat()},
        headers=headers,
    )
    assert r2.status_code == 409


async def test_xp_events_are_stamped_with_the_active_season(client, db_session, monkeypatch):
    db_session.add(Game(**GAME_2048))
    await db_session.commit()
    monkeypatch.setattr(settings, "admin_telegram_ids", "9502")
    admin_headers = await _auth(client, 9502)

    now = datetime.now(UTC)
    r = await client.post(
        "/api/v1/admin/seasons",
        json={"name": "Season 1", "starts_at": now.isoformat(), "ends_at": (now + timedelta(days=30)).isoformat()},
        headers=admin_headers,
    )
    season_id = r.json()["id"]

    player_headers = await _auth(client, 9503)
    await _play_and_finish(client, db_session, player_headers, 6000)

    row = (await db_session.execute(select(XpEvent).where(XpEvent.source == "game"))).scalar_one()
    assert row.season_id == season_id


async def test_season_leaderboard_and_no_active_season_404(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "admin_telegram_ids", "9504")
    headers = await _auth(client, 9504)

    r = await client.get("/api/v1/leaderboards/season", headers=headers)
    assert r.status_code == 404

    now = datetime.now(UTC)
    await client.post(
        "/api/v1/admin/seasons",
        json={"name": "Season 1", "starts_at": now.isoformat(), "ends_at": (now + timedelta(days=30)).isoformat()},
        headers=headers,
    )

    db_session.add(Game(**GAME_2048))
    await db_session.commit()
    other_headers = await _auth(client, 9505)
    await _play_and_finish(client, db_session, other_headers, 9000)
    await _play_and_finish(client, db_session, headers, 2000)

    r = await client.get("/api/v1/leaderboards/season", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["entries"][0]["user_id"] != body["entries"][1]["user_id"]
    assert body["entries"][0]["score"] >= body["entries"][1]["score"]
    assert body["my_rank"] is not None


async def test_finalize_season_freezes_results_pays_rank_xp_and_starts_next(client, db_session, monkeypatch):
    db_session.add(Game(**GAME_2048))
    await db_session.commit()
    monkeypatch.setattr(settings, "admin_telegram_ids", "9506")
    admin_headers = await _auth(client, 9506)

    now = datetime.now(UTC)
    r = await client.post(
        "/api/v1/admin/seasons",
        json={"name": "Season 1", "starts_at": now.isoformat(), "ends_at": (now + timedelta(days=30)).isoformat()},
        headers=admin_headers,
    )
    season_id = r.json()["id"]

    winner_headers = await _auth(client, 9507)
    await _play_and_finish(client, db_session, winner_headers, 9000)

    winner = (await db_session.execute(select(User).where(User.telegram_id == 9507))).scalar_one()
    xp_before = winner.total_xp

    r2 = await client.post(f"/api/v1/admin/seasons/{season_id}/finalize", headers=admin_headers)
    assert r2.status_code == 200
    assert r2.json()["status"] == "ended"

    result = (
        await db_session.execute(select(SeasonResult).where(SeasonResult.season_id == season_id, SeasonResult.user_id == winner.id))
    ).scalar_one()
    assert result.rank == 1
    assert result.xp_awarded == 500  # default rank-1 reward

    await db_session.refresh(winner)
    assert winner.total_xp == xp_before + 500

    # A new season auto-started, back-to-back.
    new_season = (await db_session.execute(select(Season).where(Season.status == "active"))).scalar_one()
    assert new_season.id != season_id
    assert new_season.name == "Season 2"
