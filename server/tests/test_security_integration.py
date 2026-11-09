"""HTTP-level security tests (plan section 18's explicit test checklist:
missing/invalid tokens, access to other users' sessions, oversized
inputs, injection attempts on string fields) — complements
test_security.py, which only unit-tests validate_init_data() in
isolation."""

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


# --- Missing/invalid tokens ---

async def test_missing_authorization_header_rejected(client, db_session):
    r = await client.get("/api/v1/me")
    assert r.status_code == 401


async def test_malformed_authorization_header_rejected(client, db_session):
    r = await client.get("/api/v1/me", headers={"Authorization": "not-a-bearer-token"})
    assert r.status_code == 401


async def test_garbage_bearer_token_rejected(client, db_session):
    r = await client.get("/api/v1/me", headers={"Authorization": "Bearer complete.garbage.token"})
    assert r.status_code == 401


async def test_token_for_banned_user_rejected(client, db_session):
    from sqlalchemy import select
    from app.models.user import User

    headers = await _auth(client, 7001)
    user = (await db_session.execute(select(User).where(User.telegram_id == 7001))).scalar_one()
    await db_session.execute(sa_update(User).where(User.id == user.id).values(is_banned=True))
    await db_session.commit()

    r = await client.get("/api/v1/me", headers=headers)
    assert r.status_code == 403


# --- Access to other users' sessions/resources ---

async def test_cannot_finish_another_users_session(client, db_session):
    db_session.add(Game(**GAME_2048))
    await db_session.commit()
    owner_headers = await _auth(client, 7002)
    attacker_headers = await _auth(client, 7003)

    r = await client.post("/api/v1/games/2048/sessions", json={}, headers=owner_headers)
    sess = r.json()
    past = datetime.now(UTC) - timedelta(seconds=30)
    await db_session.execute(
        sa_update(GameSession).where(GameSession.id == uuid.UUID(sess["session_id"])).values(started_at=past)
    )
    await db_session.commit()

    r2 = await client.post(
        f"/api/v1/sessions/{sess['session_id']}/finish",
        json={"token": sess["token"], "score": 1000}, headers=attacker_headers,
    )
    assert r2.status_code == 404  # same 404 as a nonexistent session — no existence leak


async def test_cannot_heartbeat_another_users_session(client, db_session):
    db_session.add(Game(**GAME_2048))
    await db_session.commit()
    owner_headers = await _auth(client, 7004)
    attacker_headers = await _auth(client, 7005)

    r = await client.post("/api/v1/games/2048/sessions", json={}, headers=owner_headers)
    session_id = r.json()["session_id"]

    r2 = await client.post(f"/api/v1/sessions/{session_id}/heartbeat", headers=attacker_headers)
    assert r2.status_code == 404


async def test_wrong_session_token_rejected(client, db_session):
    db_session.add(Game(**GAME_2048))
    await db_session.commit()
    headers = await _auth(client, 7006)

    r = await client.post("/api/v1/games/2048/sessions", json={}, headers=headers)
    sess = r.json()
    past = datetime.now(UTC) - timedelta(seconds=30)
    await db_session.execute(
        sa_update(GameSession).where(GameSession.id == uuid.UUID(sess["session_id"])).values(started_at=past)
    )
    await db_session.commit()

    r2 = await client.post(
        f"/api/v1/sessions/{sess['session_id']}/finish",
        json={"token": "completely-wrong-token", "score": 1000}, headers=headers,
    )
    assert r2.status_code == 401


# --- Oversized inputs ---

async def test_oversized_string_field_does_not_crash_the_server(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "admin_telegram_ids", "7007")
    headers = await _auth(client, 7007)
    huge = "x" * 2_000_000  # 2MB in one field

    r = await client.post(
        "/api/v1/admin/sponsors", json={"name": huge, "contact_email": None}, headers=headers
    )
    # Whatever it decides (accept it, or reject it) it must not 500 —
    # a crash here would mean an attacker found a way to take the
    # process down with one oversized field.
    assert r.status_code != 500


async def test_oversized_request_body_does_not_crash_the_server(client, db_session):
    headers = await _auth(client, 7008)
    r = await client.post(
        "/api/v1/games/2048/sessions", content=b"{" + b"1" * 5_000_000, headers={**headers, "Content-Type": "application/json"}
    )
    assert r.status_code != 500


# --- Injection attempts on string fields ---

async def test_sql_injection_like_strings_in_search_are_treated_as_literal_data(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "admin_telegram_ids", "7009")
    headers = await _auth(client, 7009)

    payloads = ["'; DROP TABLE users; --", "' OR '1'='1", "%' OR 1=1 --", "\x00\x01malicious"]
    for payload in payloads:
        r = await client.get("/api/v1/admin/users", params={"search": payload}, headers=headers)
        assert r.status_code == 200
        assert r.json() == []  # no such user — the string was never executed as SQL, just compared as data

    # The users table must still exist and be queryable afterward.
    r2 = await client.get("/api/v1/admin/users", headers=headers)
    assert r2.status_code == 200


async def test_injection_like_game_slug_is_treated_as_literal_data(client, db_session):
    headers = await _auth(client, 7010)
    r = await client.get("/api/v1/games/'; DROP TABLE games; --", headers=headers)
    assert r.status_code == 404  # just "not found," not a server error

    r2 = await client.get("/api/v1/games", headers=headers)
    assert r2.status_code == 200


# --- Response headers ---

async def test_security_headers_present_on_every_response(client, db_session):
    r = await client.get("/healthz")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["referrer-policy"] == "no-referrer"
    assert "strict-transport-security" in r.headers
    # Deliberately absent — see app/main.py's comment on why a Mini App
    # can't set a framing restriction.
    assert "x-frame-options" not in r.headers
