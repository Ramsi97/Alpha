"""Integration test for the admin analytics overview (plan section 21/B5)."""

import hashlib
import hmac
import json
import time
import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from sqlalchemy import update as sa_update

from app.core.config import settings
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


async def test_analytics_overview_reflects_real_activity(client, db_session, monkeypatch):
    db_session.add(Game(**GAME_2048))
    await db_session.commit()
    monkeypatch.setattr(settings, "admin_telegram_ids", "9801")
    admin_headers = await _auth(client, 9801)

    player_headers = await _auth(client, 9802)
    await _play_and_finish(client, db_session, player_headers, 5000)

    r = await client.get("/api/v1/admin/analytics/overview", headers=admin_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["dau"] >= 1
    assert any(row["game_slug"] == "2048" and row["runs_last_7_days"] >= 1 for row in body["runs_per_game"])


async def test_analytics_overview_handles_empty_cohorts_gracefully(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "admin_telegram_ids", "9803")
    admin_headers = await _auth(client, 9803)

    r = await client.get("/api/v1/admin/analytics/overview", headers=admin_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["day1_retention"] is None
    assert body["task_completion_rate"] is None
    assert body["referral_conversion"] is None


async def test_non_admin_cannot_access_analytics(client, db_session):
    headers = await _auth(client, 9804)
    r = await client.get("/api/v1/admin/analytics/overview", headers=headers)
    assert r.status_code == 403
