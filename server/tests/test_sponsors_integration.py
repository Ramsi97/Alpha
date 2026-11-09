"""Integration tests for sponsors and sponsor reports (plan section 16/B5)."""

import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

from sqlalchemy import select

from app.core.config import settings
from app.models.task import Task


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


async def test_create_sponsor_and_associate_a_task(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "admin_telegram_ids", "9701")
    admin_headers = await _auth(client, 9701)

    r = await client.post(
        "/api/v1/admin/sponsors", json={"name": "Acme Co", "contact_email": "ads@acme.test"}, headers=admin_headers
    )
    assert r.status_code == 200, r.text
    sponsor_id = r.json()["id"]

    r2 = await client.post(
        "/api/v1/admin/tasks",
        json={
            "type": "custom", "title": {"en": "Visit Acme"}, "description": {"en": "d"},
            "xp_reward": 20, "verify_method": "manual", "sponsor_id": sponsor_id,
        },
        headers=admin_headers,
    )
    assert r2.status_code == 200, r2.text
    task_id = r2.json()["id"]

    task = (await db_session.execute(select(Task).where(Task.id == task_id))).scalar_one()
    assert task.sponsor_id == sponsor_id


async def test_sponsor_report_counts_completions_and_xp(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "admin_telegram_ids", "9702")
    admin_headers = await _auth(client, 9702)

    r = await client.post("/api/v1/admin/sponsors", json={"name": "Acme Co"}, headers=admin_headers)
    sponsor_id = r.json()["id"]

    r2 = await client.post(
        "/api/v1/admin/tasks",
        json={
            "type": "custom", "title": {"en": "Visit Acme"}, "description": {"en": "d"},
            "xp_reward": 20, "verify_method": "manual", "sponsor_id": sponsor_id,
        },
        headers=admin_headers,
    )
    task_id = r2.json()["id"]

    player1 = await _auth(client, 9703)
    player2 = await _auth(client, 9704)
    for player_headers in (player1, player2):
        await client.post(f"/api/v1/tasks/{task_id}/start", headers=player_headers)
        verify = await client.post(f"/api/v1/tasks/{task_id}/verify", headers=player_headers)
        assert verify.json()["status"] == "pending_review"

    pending = (await client.get("/api/v1/admin/tasks/review-queue", headers=admin_headers)).json()
    for row in pending:
        await client.post(f"/api/v1/admin/user-tasks/{row['id']}/approve", headers=admin_headers)

    report = await client.get(f"/api/v1/admin/sponsors/{sponsor_id}/report", headers=admin_headers)
    assert report.status_code == 200, report.text
    body = report.json()
    assert body["total_completions"] == 2
    assert body["total_xp_awarded"] == 40
    assert body["tasks"][0]["task_id"] == task_id


async def test_report_for_unknown_sponsor_404(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "admin_telegram_ids", "9705")
    admin_headers = await _auth(client, 9705)
    r = await client.get("/api/v1/admin/sponsors/99999/report", headers=admin_headers)
    assert r.status_code == 404
