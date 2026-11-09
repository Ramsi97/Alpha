"""Integration tests for B3's admin surface: task CRUD/review-queue,
user search/ban/XP-adjust, flagged-score approve/reject, notifications."""

import hashlib
import hmac
import json
import time
import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from sqlalchemy import select, update as sa_update

from app.core.config import settings
from app.core.telegram_client import FakeTelegramClient, SendResult, get_telegram_client
from app.models.game import Game
from app.models.notification import NotificationOutbox
from app.models.score import Score
from app.models.session import GameSession
from app.models.task import Task, UserTask
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


async def _admin_headers(client, telegram_id: int, monkeypatch) -> dict:
    monkeypatch.setattr(settings, "admin_telegram_ids", str(telegram_id))
    return await _auth(client, telegram_id)


# --- Task CRUD + review queue ---

async def test_admin_can_create_and_list_tasks(client, db_session, monkeypatch):
    headers = await _admin_headers(client, 7201, monkeypatch)
    r = await client.post("/api/v1/admin/tasks", json={
        "type": "custom", "title": {"en": "Do a thing"}, "xp_reward": 25, "verify_method": "manual",
    }, headers=headers)
    assert r.status_code == 200
    task_id = r.json()["id"]
    assert isinstance(task_id, int)

    r2 = await client.get("/api/v1/admin/tasks", headers=headers)
    assert any(t["id"] == task_id for t in r2.json())


async def test_admin_can_patch_task(client, db_session, monkeypatch):
    headers = await _admin_headers(client, 7202, monkeypatch)
    r = await client.post("/api/v1/admin/tasks", json={
        "type": "custom", "title": {"en": "t"}, "xp_reward": 10, "verify_method": "manual",
    }, headers=headers)
    task_id = r.json()["id"]

    r2 = await client.patch(f"/api/v1/admin/tasks/{task_id}", json={"active": False}, headers=headers)
    assert r2.json()["active"] is False


async def test_review_queue_approve_awards_xp(client, db_session, monkeypatch):
    headers = await _admin_headers(client, 7203, monkeypatch)
    r = await client.post("/api/v1/admin/tasks", json={
        "type": "custom", "title": {"en": "t"}, "xp_reward": 30, "verify_method": "manual",
    }, headers=headers)
    task_id = r.json()["id"]

    player_headers = await _auth(client, 7204)
    await client.post(f"/api/v1/tasks/{task_id}/start", headers=player_headers)
    await client.post(f"/api/v1/tasks/{task_id}/verify", headers=player_headers)  # -> pending_review

    r2 = await client.get("/api/v1/admin/tasks/review-queue", headers=headers)
    assert len(r2.json()) == 1
    user_task_id = r2.json()[0]["id"]

    r3 = await client.post(f"/api/v1/admin/user-tasks/{user_task_id}/approve", headers=headers)
    assert r3.json()["status"] == "completed"

    me = await client.get("/api/v1/me", headers=player_headers)
    assert me.json()["total_xp"] == 30


async def test_review_queue_reject_awards_nothing(client, db_session, monkeypatch):
    headers = await _admin_headers(client, 7205, monkeypatch)
    r = await client.post("/api/v1/admin/tasks", json={
        "type": "custom", "title": {"en": "t"}, "xp_reward": 30, "verify_method": "manual",
    }, headers=headers)
    task_id = r.json()["id"]

    player_headers = await _auth(client, 7206)
    await client.post(f"/api/v1/tasks/{task_id}/start", headers=player_headers)
    await client.post(f"/api/v1/tasks/{task_id}/verify", headers=player_headers)

    r2 = await client.get("/api/v1/admin/tasks/review-queue", headers=headers)
    user_task_id = r2.json()[0]["id"]

    r3 = await client.post(f"/api/v1/admin/user-tasks/{user_task_id}/reject", headers=headers)
    assert r3.json()["status"] == "rejected"

    me = await client.get("/api/v1/me", headers=player_headers)
    assert me.json()["total_xp"] == 0


# --- Users ---

async def test_admin_search_users_by_telegram_id(client, db_session, monkeypatch):
    await _auth(client, 7301)
    headers = await _admin_headers(client, 7302, monkeypatch)

    r = await client.get("/api/v1/admin/users", params={"search": "7301"}, headers=headers)
    assert len(r.json()) == 1
    assert r.json()[0]["telegram_id"] == 7301


async def test_admin_ban_and_unban_user(client, db_session, monkeypatch):
    player_headers = await _auth(client, 7303)
    headers = await _admin_headers(client, 7304, monkeypatch)

    user = (await db_session.execute(select(User).where(User.telegram_id == 7303))).scalar_one()

    r = await client.post(f"/api/v1/admin/users/{user.id}/ban", headers=headers)
    assert r.json()["is_banned"] is True

    # Banned user is now rejected by the normal auth dependency.
    r2 = await client.get("/api/v1/me", headers=player_headers)
    assert r2.status_code == 403

    await client.post(f"/api/v1/admin/users/{user.id}/unban", headers=headers)
    r3 = await client.get("/api/v1/me", headers=player_headers)
    assert r3.status_code == 200


async def test_admin_xp_adjustment_writes_ledger_and_updates_total(client, db_session, monkeypatch):
    player_headers = await _auth(client, 7305)
    headers = await _admin_headers(client, 7306, monkeypatch)
    user = (await db_session.execute(select(User).where(User.telegram_id == 7305))).scalar_one()

    r = await client.post(
        f"/api/v1/admin/users/{user.id}/adjust-xp",
        json={"amount": 100, "reason": "compensation"}, headers=headers,
    )
    assert r.json()["total_xp"] == 100

    rows = (await db_session.execute(select(XpEvent).where(XpEvent.user_id == user.id))).scalars().all()
    assert len(rows) == 1
    assert rows[0].source == "admin"
    assert rows[0].amount == 100

    # Negative adjustment (reversal) also works.
    r2 = await client.post(
        f"/api/v1/admin/users/{user.id}/adjust-xp",
        json={"amount": -40, "reason": "fraud reversal"}, headers=headers,
    )
    assert r2.json()["total_xp"] == 60


# --- Flagged scores ---

async def _create_flagged_score(client, db_session, telegram_id) -> tuple[dict, int]:
    db_session.add(Game(**GAME_2048))
    await db_session.commit()
    headers = await _auth(client, telegram_id)
    r = await client.post("/api/v1/games/2048/sessions", json={}, headers=headers)
    sess = r.json()
    past = datetime.now(UTC) - timedelta(seconds=20)
    await db_session.execute(
        sa_update(GameSession).where(GameSession.id == uuid.UUID(sess["session_id"])).values(started_at=past)
    )
    await db_session.commit()
    r2 = await client.post(
        f"/api/v1/sessions/{sess['session_id']}/finish",
        json={"token": sess["token"], "score": 500000}, headers=headers,  # flagged
    )
    assert r2.json()["flagged"] is True
    score_row = (await db_session.execute(select(Score).where(Score.session_id == uuid.UUID(sess["session_id"])))).scalar_one()
    return headers, score_row.id


async def test_flagged_scores_appear_in_review_queue(client, db_session, monkeypatch):
    _player_headers, score_id = await _create_flagged_score(client, db_session, 7401)
    headers = await _admin_headers(client, 7402, monkeypatch)

    r = await client.get("/api/v1/admin/flagged-scores", headers=headers)
    assert any(s["id"] == score_id for s in r.json())


async def test_approve_flagged_score_awards_xp(client, db_session, monkeypatch):
    player_headers, score_id = await _create_flagged_score(client, db_session, 7403)
    headers = await _admin_headers(client, 7404, monkeypatch)

    r = await client.post(f"/api/v1/admin/flagged-scores/{score_id}/approve", headers=headers)
    assert r.json()["xp_awarded"] == 300  # capped by max_xp_per_run

    me = await client.get("/api/v1/me", headers=player_headers)
    assert me.json()["total_xp"] == 300

    # Can't review the same score twice.
    r2 = await client.post(f"/api/v1/admin/flagged-scores/{score_id}/approve", headers=headers)
    assert r2.status_code == 409


async def test_reject_flagged_score_awards_nothing(client, db_session, monkeypatch):
    player_headers, score_id = await _create_flagged_score(client, db_session, 7405)
    headers = await _admin_headers(client, 7406, monkeypatch)

    r = await client.post(f"/api/v1/admin/flagged-scores/{score_id}/reject", headers=headers)
    assert r.status_code == 200

    me = await client.get("/api/v1/me", headers=player_headers)
    assert me.json()["total_xp"] == 0

    r2 = await client.get("/api/v1/admin/flagged-scores", headers=headers)
    assert not any(s["id"] == score_id for s in r2.json())  # dropped off the queue


# --- Notifications ---

async def test_level_up_queues_a_notification_that_gets_sent(client, db_session, monkeypatch):
    db_session.add(Game(**GAME_2048))
    await db_session.commit()
    headers = await _admin_headers(client, 7501, monkeypatch)
    player_headers = await _auth(client, 7502)

    r = await client.post("/api/v1/games/2048/sessions", json={}, headers=player_headers)
    sess = r.json()
    past = datetime.now(UTC) - timedelta(seconds=30)
    await db_session.execute(
        sa_update(GameSession).where(GameSession.id == uuid.UUID(sess["session_id"])).values(started_at=past)
    )
    await db_session.commit()
    await client.post(
        f"/api/v1/sessions/{sess['session_id']}/finish",
        json={"token": sess["token"], "score": 20000}, headers=player_headers,  # -> level 2
    )

    rows = (await db_session.execute(select(NotificationOutbox).where(NotificationOutbox.type == "level_up"))).scalars().all()
    assert len(rows) == 1
    assert rows[0].payload == {"level": 2}

    from app.main import app
    fake = FakeTelegramClient()
    app.dependency_overrides[get_telegram_client] = lambda: fake

    r2 = await client.post("/api/v1/admin/notifications/process", headers=headers)
    assert r2.json()["sent"] == 1
    assert len(fake.sent_messages) == 1
    assert "level 2" in fake.sent_messages[0][1].lower() or "2" in fake.sent_messages[0][1]

    del app.dependency_overrides[get_telegram_client]


async def test_notification_worker_marks_blocked_user_and_skips(client, db_session, monkeypatch):
    headers = await _admin_headers(client, 7503, monkeypatch)
    player_headers = await _auth(client, 7504)
    user = (await db_session.execute(select(User).where(User.telegram_id == 7504))).scalar_one()

    db_session.add(NotificationOutbox(user_id=user.id, type="streak_reminder", payload={}))
    await db_session.commit()

    from app.main import app
    fake = FakeTelegramClient()
    fake.send_results[7504] = SendResult(ok=False, blocked=True)
    app.dependency_overrides[get_telegram_client] = lambda: fake

    r = await client.post("/api/v1/admin/notifications/process", headers=headers)
    assert r.json()["skipped"] == 1

    await db_session.refresh(user)
    assert user.bot_blocked is True

    del app.dependency_overrides[get_telegram_client]
