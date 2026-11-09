"""Integration tests for the self-service data-deletion path (plan
section 18: "Provide a simple data-deletion path for users who ask")."""

import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

from sqlalchemy import select

from app.core.config import settings
from app.models.user import User


def make_init_data(telegram_id: int) -> str:
    user = json.dumps({
        "id": telegram_id, "first_name": f"P{telegram_id}", "username": f"user{telegram_id}",
        "language_code": "en",
    })
    pairs = {"auth_date": str(int(time.time())), "user": user}
    data_check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", settings.bot_token.encode(), hashlib.sha256).digest()
    pairs["hash"] = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    return urlencode(pairs)


async def _auth(client, telegram_id: int) -> dict:
    r = await client.post("/api/v1/auth/telegram", json={"init_data": make_init_data(telegram_id)})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def test_delete_me_anonymizes_pii_but_keeps_the_row(client, db_session):
    headers = await _auth(client, 8201)

    r = await client.delete("/api/v1/me", headers=headers)
    assert r.status_code == 204

    user = (await db_session.execute(select(User).where(User.telegram_id == 8201))).scalar_one()
    assert user.username is None
    assert user.first_name is None
    assert user.deleted_at is not None
    assert user.notifications_enabled is False
    assert user.telegram_id == 8201  # the row itself survives


async def test_old_token_rejected_after_deletion(client, db_session):
    headers = await _auth(client, 8202)
    await client.delete("/api/v1/me", headers=headers)

    r = await client.get("/api/v1/me", headers=headers)
    assert r.status_code == 401


async def test_reauthenticating_after_deletion_restores_access(client, db_session):
    headers = await _auth(client, 8203)
    await client.delete("/api/v1/me", headers=headers)

    new_headers = await _auth(client, 8203)  # fresh initData == renewed consent
    r = await client.get("/api/v1/me", headers=new_headers)
    assert r.status_code == 200
    assert r.json()["username"] == "user8203"  # fresh profile data restored

    user = (await db_session.execute(select(User).where(User.telegram_id == 8203))).scalar_one()
    assert user.deleted_at is None
    assert user.notifications_enabled is True
