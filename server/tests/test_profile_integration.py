"""Integration tests for /me, /me/xp-history, and /achievements."""

import hashlib
import hmac
import json
import time
import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from sqlalchemy import update as sa_update

from app.core.config import settings
from app.models.achievement import Achievement
from app.models.game import Game
from app.models.session import GameSession

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


async def test_me_includes_level_progress_and_achievements_count(client, db_session):
    headers = await _auth(client, 8201)
    r = await client.get("/api/v1/me", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["level_progress"] == {"current_level_xp": 0, "xp_for_next_level": 100}
    assert body["achievements_unlocked"] == 0


async def test_auth_response_also_includes_level_progress(client, db_session):
    r = await client.post("/api/v1/auth/telegram", json={"init_data": make_init_data(8202)})
    assert r.json()["user"]["level_progress"] == {"current_level_xp": 0, "xp_for_next_level": 100}


async def test_patch_me_updates_language(client, db_session):
    headers = await _auth(client, 8203)
    r = await client.patch("/api/v1/me", json={"language": "am"}, headers=headers)
    assert r.json()["language"] == "am"


async def test_xp_history_pagination(client, db_session):
    db_session.add(Game(**GAME_2048))
    await db_session.commit()
    headers = await _auth(client, 8204)

    # Generate several XP-earning runs to populate the ledger.
    for _ in range(5):
        r = await client.post("/api/v1/games/2048/sessions", json={}, headers=headers)
        sess = r.json()
        past = datetime.now(UTC) - timedelta(seconds=30)
        await db_session.execute(
            sa_update(GameSession).where(GameSession.id == uuid.UUID(sess["session_id"])).values(started_at=past)
        )
        await db_session.commit()
        await client.post(
            f"/api/v1/sessions/{sess['session_id']}/finish",
            json={"token": sess["token"], "score": 1000}, headers=headers,
        )

    r = await client.get("/api/v1/me/xp-history", params={"limit": 2}, headers=headers)
    assert r.status_code == 200
    page1 = r.json()
    assert len(page1["entries"]) == 2
    assert page1["next_cursor"] is not None
    # newest first
    assert page1["entries"][0]["id"] > page1["entries"][1]["id"]

    r2 = await client.get(
        "/api/v1/me/xp-history", params={"limit": 2, "cursor": page1["next_cursor"]}, headers=headers
    )
    page2 = r2.json()
    assert len(page2["entries"]) == 2
    # no overlap with page 1
    page1_ids = {e["id"] for e in page1["entries"]}
    page2_ids = {e["id"] for e in page2["entries"]}
    assert page1_ids.isdisjoint(page2_ids)


async def test_achievements_list_shows_unlocked_state(client, db_session):
    db_session.add(Achievement(
        key="test_ach", title={"en": "Test"}, description={"en": "d"}, icon="x",
        condition={"type": "level", "value": 99}, xp_reward=0,
    ))
    await db_session.commit()
    headers = await _auth(client, 8205)

    r = await client.get("/api/v1/achievements", headers=headers)
    assert r.status_code == 200
    entries = r.json()
    assert len(entries) == 1
    assert entries[0]["key"] == "test_ach"
    assert entries[0]["unlocked"] is False
    assert entries[0]["unlocked_at"] is None
