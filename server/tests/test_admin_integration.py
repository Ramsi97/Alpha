"""Integration tests for admin bootstrap, access control, and the basic
admin endpoints (plan section 16)."""

import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

from sqlalchemy import select

from app.core.config import settings
from app.models.admin import AdminUser, AuditLog
from app.models.game import Game

GAME_2048 = dict(
    slug="2048", version="1.0.0", title={"en": "2048"}, description={"en": "d"},
    category="number-puzzle", thumbnail_url="t.svg", entry_url="http://x/2048/index.html",
    variants=[], max_score=500000, min_play_seconds=20, max_score_per_second=1000,
    xp_rate=0.01, max_xp_per_run=300, license_code="MIT", license_assets="none",
    author="a", source_url="http://x", size_kb=136, status="pending",
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


async def test_non_admin_cannot_access_admin_endpoints(client, db_session):
    headers = await _auth(client, 9301)
    r = await client.get("/api/v1/admin/games", headers=headers)
    assert r.status_code == 403


async def test_admin_bootstrap_from_settings_and_access_granted(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "admin_telegram_ids", "9302")
    headers = await _auth(client, 9302)

    r = await client.get("/api/v1/admin/games", headers=headers)
    assert r.status_code == 200

    # And actually got a real admin_users row, not just a lucky pass.
    from app.models.user import User
    user = (await db_session.execute(select(User).where(User.telegram_id == 9302))).scalar_one()
    admin_row = (await db_session.execute(select(AdminUser).where(AdminUser.user_id == user.id))).scalar_one_or_none()
    assert admin_row is not None


async def test_admin_patch_game_activates_and_tunes_xp_rate(client, db_session, monkeypatch):
    db_session.add(Game(**GAME_2048))
    await db_session.commit()

    monkeypatch.setattr(settings, "admin_telegram_ids", "9303")
    headers = await _auth(client, 9303)

    r = await client.patch(
        "/api/v1/admin/games/2048", json={"status": "active", "xp_rate": 0.02}, headers=headers
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "active"
    assert body["xp_rate"] == 0.02

    # Now visible via the public catalog endpoint.
    r2 = await client.get("/api/v1/games", headers=headers)
    assert any(g["slug"] == "2048" for g in r2.json())


async def test_admin_patch_game_rejects_invalid_status(client, db_session, monkeypatch):
    db_session.add(Game(**GAME_2048))
    await db_session.commit()
    monkeypatch.setattr(settings, "admin_telegram_ids", "9304")
    headers = await _auth(client, 9304)

    r = await client.patch("/api/v1/admin/games/2048", json={"status": "nonsense"}, headers=headers)
    assert r.status_code == 400


async def test_admin_game_patch_writes_audit_log(client, db_session, monkeypatch):
    db_session.add(Game(**GAME_2048))
    await db_session.commit()
    monkeypatch.setattr(settings, "admin_telegram_ids", "9305")
    headers = await _auth(client, 9305)

    await client.patch("/api/v1/admin/games/2048", json={"status": "active"}, headers=headers)

    rows = (await db_session.execute(select(AuditLog).where(AuditLog.action == "game.update"))).scalars().all()
    assert len(rows) == 1
    assert rows[0].target_id == "2048"
    assert rows[0].details == {"status": "active"}


async def test_admin_settings_get_and_put(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "admin_telegram_ids", "9306")
    headers = await _auth(client, 9306)

    r = await client.get("/api/v1/admin/settings/daily_game_xp_cap", headers=headers)
    assert r.status_code == 404

    r2 = await client.put(
        "/api/v1/admin/settings/daily_game_xp_cap", json={"value": 1500}, headers=headers
    )
    assert r2.status_code == 200
    assert r2.json()["value"] == 1500

    r3 = await client.get("/api/v1/admin/settings/daily_game_xp_cap", headers=headers)
    assert r3.json()["value"] == 1500
