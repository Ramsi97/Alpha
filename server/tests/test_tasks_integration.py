"""Integration tests for the task engine (plan section 12)."""

import hashlib
import hmac
import json
import time
import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from sqlalchemy import update as sa_update

from app.core.config import settings
from app.core.telegram_client import FakeTelegramClient, get_telegram_client
from app.models.game import Game
from app.models.session import GameSession
from app.models.task import Task, UserTask

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


async def _add_task(db_session, **overrides) -> Task:
    defaults = dict(
        type="custom", title={"en": "t"}, description={"en": "d"}, payload={},
        xp_reward=10, period="once", verify_method="manual", active=True,
    )
    task = Task(**{**defaults, **overrides})
    db_session.add(task)
    await db_session.commit()
    return task


async def test_open_link_timed_claim_not_ready_immediately(client, db_session):
    task = await _add_task(
        db_session, type="open_link", verify_method="timed_claim",
        payload={"min_wait_seconds": 15}, xp_reward=5,
    )
    headers = await _auth(client, 7101)

    r = await client.post(f"/api/v1/tasks/{task.id}/start", headers=headers)
    assert r.status_code == 200

    r2 = await client.post(f"/api/v1/tasks/{task.id}/verify", headers=headers)
    assert r2.json()["status"] == "started"  # not enough time has passed
    assert r2.json()["xp_awarded"] == 0


async def test_open_link_timed_claim_completes_after_wait(client, db_session):
    task = await _add_task(
        db_session, type="open_link", verify_method="timed_claim",
        payload={"min_wait_seconds": 15}, xp_reward=5,
    )
    headers = await _auth(client, 7102)
    await client.post(f"/api/v1/tasks/{task.id}/start", headers=headers)

    # Backdate the user_task's started_at so the wait "already happened".
    await db_session.execute(
        sa_update(UserTask).where(UserTask.task_id == task.id).values(
            started_at=datetime.now(UTC) - timedelta(seconds=30)
        )
    )
    await db_session.commit()

    r = await client.post(f"/api/v1/tasks/{task.id}/verify", headers=headers)
    assert r.json()["status"] == "completed"
    assert r.json()["xp_awarded"] == 5


async def test_custom_manual_task_goes_to_pending_review(client, db_session):
    task = await _add_task(db_session, type="custom", verify_method="manual", xp_reward=20)
    headers = await _auth(client, 7103)
    await client.post(f"/api/v1/tasks/{task.id}/start", headers=headers)

    r = await client.post(f"/api/v1/tasks/{task.id}/verify", headers=headers)
    assert r.json()["status"] == "pending_review"
    assert r.json()["xp_awarded"] == 0


async def test_daily_open_completes_after_real_checkin(client, db_session):
    task = await _add_task(db_session, type="daily_open", verify_method="auto", period="daily", xp_reward=8)
    headers = await _auth(client, 7104)
    await client.post(f"/api/v1/tasks/{task.id}/start", headers=headers)

    r = await client.post(f"/api/v1/tasks/{task.id}/verify", headers=headers)
    assert r.json()["status"] == "started"  # haven't checked in yet

    await client.post("/api/v1/checkin", headers=headers)

    r2 = await client.post(f"/api/v1/tasks/{task.id}/verify", headers=headers)
    assert r2.json()["status"] == "completed"
    assert r2.json()["xp_awarded"] == 8


async def test_play_game_task_requires_matching_score(client, db_session):
    db_session.add(Game(**GAME_2048))
    await db_session.commit()
    task = await _add_task(
        db_session, type="play_game", verify_method="auto",
        payload={"game_slug": "2048", "min_score": 5000}, xp_reward=15,
    )
    headers = await _auth(client, 7105)
    await client.post(f"/api/v1/tasks/{task.id}/start", headers=headers)

    r = await client.post(f"/api/v1/tasks/{task.id}/verify", headers=headers)
    assert r.json()["status"] == "started"  # no runs yet

    # Play a run below the threshold.
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
    r2 = await client.post(f"/api/v1/tasks/{task.id}/verify", headers=headers)
    assert r2.json()["status"] == "started"  # below min_score

    # Now play a run that clears it.
    r = await client.post("/api/v1/games/2048/sessions", json={}, headers=headers)
    sess = r.json()
    await db_session.execute(
        sa_update(GameSession).where(GameSession.id == uuid.UUID(sess["session_id"])).values(started_at=past)
    )
    await db_session.commit()
    await client.post(
        f"/api/v1/sessions/{sess['session_id']}/finish",
        json={"token": sess["token"], "score": 6000}, headers=headers,
    )
    r3 = await client.post(f"/api/v1/tasks/{task.id}/verify", headers=headers)
    assert r3.json()["status"] == "completed"
    assert r3.json()["xp_awarded"] == 15


async def test_join_channel_uses_fake_telegram_client(client, db_session):
    task = await _add_task(
        db_session, type="join_channel", verify_method="auto",
        payload={"chat_id": "@testchannel"}, xp_reward=12,
    )
    headers = await _auth(client, 7106)
    await client.post(f"/api/v1/tasks/{task.id}/start", headers=headers)

    fake = FakeTelegramClient()  # not a member yet
    from app.main import app
    app.dependency_overrides[get_telegram_client] = lambda: fake

    r = await client.post(f"/api/v1/tasks/{task.id}/verify", headers=headers)
    assert r.json()["status"] == "started"

    # Join the channel in the fake client, then verify again.
    fake.chat_member_statuses[("@testchannel", 7106)] = "member"
    r2 = await client.post(f"/api/v1/tasks/{task.id}/verify", headers=headers)
    assert r2.json()["status"] == "completed"
    assert r2.json()["xp_awarded"] == 12

    del app.dependency_overrides[get_telegram_client]


async def test_task_completion_does_not_double_award(client, db_session):
    task = await _add_task(db_session, type="custom", verify_method="manual", xp_reward=20)
    # manual tasks can't double-complete via verify alone, so test via a
    # type that can complete on its own: open_link.
    task2 = await _add_task(
        db_session, type="open_link", verify_method="timed_claim",
        payload={"min_wait_seconds": 0}, xp_reward=7,
    )
    headers = await _auth(client, 7107)
    await client.post(f"/api/v1/tasks/{task2.id}/start", headers=headers)

    r1 = await client.post(f"/api/v1/tasks/{task2.id}/verify", headers=headers)
    assert r1.json()["status"] == "completed"
    r2 = await client.post(f"/api/v1/tasks/{task2.id}/verify", headers=headers)
    # already completed: verify_task short-circuits on non-'started' status
    assert r2.json()["status"] == "completed"
    assert r2.json()["xp_awarded"] == 0  # not re-awarded


async def test_max_total_completions_caps_globally(client, db_session):
    task = await _add_task(
        db_session, type="open_link", verify_method="timed_claim",
        payload={"min_wait_seconds": 0}, xp_reward=5, max_total_completions=1,
    )
    headers_a = await _auth(client, 7108)
    headers_b = await _auth(client, 7109)

    await client.post(f"/api/v1/tasks/{task.id}/start", headers=headers_a)
    ra = await client.post(f"/api/v1/tasks/{task.id}/verify", headers=headers_a)
    assert ra.json()["status"] == "completed"

    await client.post(f"/api/v1/tasks/{task.id}/start", headers=headers_b)
    rb = await client.post(f"/api/v1/tasks/{task.id}/verify", headers=headers_b)
    assert rb.json()["status"] == "started"  # cap already reached
