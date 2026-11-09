"""Integration tests for tournaments (plan section 13): join, score
recording under each rule, and the closing job (rank + rank XP)."""

import hashlib
import hmac
import json
import time
import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from sqlalchemy import select

from app.core.config import settings
from app.models.game import Game
from app.models.session import GameSession
from app.models.user import User
from sqlalchemy import update as sa_update

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
    assert r2.status_code == 200, r2.text
    return r2.json()


async def _create_tournament(client, admin_headers, rule="best_score", top_n=None) -> int:
    now = datetime.now(UTC)
    r = await client.post(
        "/api/v1/admin/tournaments",
        json={
            "title": {"en": "Weekend Cup"}, "game_slug": "2048", "rule": rule, "top_n": top_n,
            "starts_at": (now - timedelta(minutes=1)).isoformat(), "ends_at": (now + timedelta(days=1)).isoformat(),
        },
        headers=admin_headers,
    )
    assert r.status_code == 200, r.text
    return r.json()["id"]


async def test_join_is_required_for_a_run_to_count(client, db_session, monkeypatch):
    db_session.add(Game(**GAME_2048))
    await db_session.commit()
    monkeypatch.setattr(settings, "admin_telegram_ids", "9601")
    admin_headers = await _auth(client, 9601)
    tournament_id = await _create_tournament(client, admin_headers)

    player_headers = await _auth(client, 9602)
    await _play_and_finish(client, db_session, player_headers, 5000)  # hasn't joined

    r = await client.get(f"/api/v1/tournaments/{tournament_id}", headers=player_headers)
    assert r.json()["my_score"] is None

    await client.post(f"/api/v1/tournaments/{tournament_id}/join", headers=player_headers)
    await _play_and_finish(client, db_session, player_headers, 5000)

    r2 = await client.get(f"/api/v1/tournaments/{tournament_id}", headers=player_headers)
    assert r2.json()["my_score"] == 5000


async def test_best_score_rule_keeps_the_highest_run(client, db_session, monkeypatch):
    db_session.add(Game(**GAME_2048))
    await db_session.commit()
    monkeypatch.setattr(settings, "admin_telegram_ids", "9603")
    admin_headers = await _auth(client, 9603)
    tournament_id = await _create_tournament(client, admin_headers, rule="best_score")

    player_headers = await _auth(client, 9604)
    await client.post(f"/api/v1/tournaments/{tournament_id}/join", headers=player_headers)
    await _play_and_finish(client, db_session, player_headers, 3000)
    await _play_and_finish(client, db_session, player_headers, 9000)
    await _play_and_finish(client, db_session, player_headers, 4000)

    r = await client.get(f"/api/v1/tournaments/{tournament_id}", headers=player_headers)
    assert r.json()["my_score"] == 9000


async def test_sum_top_n_rule_sums_the_best_n_runs(client, db_session, monkeypatch):
    db_session.add(Game(**GAME_2048))
    await db_session.commit()
    monkeypatch.setattr(settings, "admin_telegram_ids", "9605")
    admin_headers = await _auth(client, 9605)
    tournament_id = await _create_tournament(client, admin_headers, rule="sum_top_n", top_n=2)

    player_headers = await _auth(client, 9606)
    await client.post(f"/api/v1/tournaments/{tournament_id}/join", headers=player_headers)
    await _play_and_finish(client, db_session, player_headers, 1000)
    await _play_and_finish(client, db_session, player_headers, 5000)
    await _play_and_finish(client, db_session, player_headers, 3000)

    r = await client.get(f"/api/v1/tournaments/{tournament_id}", headers=player_headers)
    assert r.json()["my_score"] == 8000  # top 2 of [1000, 5000, 3000]


async def test_closing_ranks_entries_and_pays_rank_xp(client, db_session, monkeypatch):
    db_session.add(Game(**GAME_2048))
    await db_session.commit()
    monkeypatch.setattr(settings, "admin_telegram_ids", "9607")
    admin_headers = await _auth(client, 9607)
    tournament_id = await _create_tournament(client, admin_headers)

    first_headers = await _auth(client, 9608)
    second_headers = await _auth(client, 9609)
    await client.post(f"/api/v1/tournaments/{tournament_id}/join", headers=first_headers)
    await client.post(f"/api/v1/tournaments/{tournament_id}/join", headers=second_headers)
    await _play_and_finish(client, db_session, first_headers, 9000)
    await _play_and_finish(client, db_session, second_headers, 1000)

    first_user = (await db_session.execute(select(User).where(User.telegram_id == 9608))).scalar_one()
    xp_before = first_user.total_xp

    r = await client.post(f"/api/v1/admin/tournaments/{tournament_id}/close", headers=admin_headers)
    assert r.status_code == 200, r.text
    entries = r.json()
    assert entries[0]["user_id"] == first_user.id
    assert entries[0]["rank"] == 1
    assert entries[1]["rank"] == 2

    await db_session.refresh(first_user)
    assert first_user.total_xp == xp_before + 300  # default rank-1 tournament reward

    r2 = await client.get(f"/api/v1/tournaments/{tournament_id}", headers=admin_headers)
    assert r2.json()["status"] == "ended"


async def test_cannot_close_twice(client, db_session, monkeypatch):
    db_session.add(Game(**GAME_2048))
    await db_session.commit()
    monkeypatch.setattr(settings, "admin_telegram_ids", "9610")
    admin_headers = await _auth(client, 9610)
    tournament_id = await _create_tournament(client, admin_headers)

    r = await client.post(f"/api/v1/admin/tournaments/{tournament_id}/close", headers=admin_headers)
    assert r.status_code == 200
    r2 = await client.post(f"/api/v1/admin/tournaments/{tournament_id}/close", headers=admin_headers)
    assert r2.status_code == 409
