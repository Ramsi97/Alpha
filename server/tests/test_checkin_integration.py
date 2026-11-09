"""Integration tests for /checkin against a real (clean, per-test) Postgres."""

import hashlib
import hmac
import json
import time
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from sqlalchemy import update as sa_update

from app.core.config import settings
from app.models.user import User


def _today():
    return datetime.now(UTC).date()


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


async def _set_checkin_state(db_session, telegram_id: int, last_checkin_date, streak_count, streak_freezes=0):
    await db_session.execute(
        sa_update(User)
        .where(User.telegram_id == telegram_id)
        .values(last_checkin_date=last_checkin_date, streak_count=streak_count, streak_freezes=streak_freezes)
    )
    await db_session.commit()


async def test_first_ever_checkin_starts_streak_at_one(client, db_session):
    headers = await _auth(client, 8001)
    r = await client.post("/api/v1/checkin", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["streak_count"] == 1
    assert body["xp_awarded"] == 10
    assert body["checked_in_today"] is True


async def test_repeat_checkin_same_day_awards_no_extra_xp(client, db_session):
    headers = await _auth(client, 8002)
    await client.post("/api/v1/checkin", headers=headers)
    r = await client.post("/api/v1/checkin", headers=headers)
    body = r.json()
    assert body["xp_awarded"] == 0
    assert body["streak_count"] == 1


async def test_checkin_yesterday_continues_streak(client, db_session):
    # _auth() already creates the user row; no need to call /checkin first
    # (doing so would create a real "checked in today" ledger entry that
    # then collides with the simulated continuation below).
    headers = await _auth(client, 8003)
    await _set_checkin_state(db_session, 8003, _today() - timedelta(days=1), streak_count=5)

    r = await client.post("/api/v1/checkin", headers=headers)
    body = r.json()
    assert body["streak_count"] == 6
    assert body["xp_awarded"] == 35  # new_streak=6, 10 + 5*min(6-1, 6) = 10 + 25
    assert body["checked_in_today"] is True


async def test_checkin_gap_of_two_days_with_freeze_continues_streak(client, db_session):
    headers = await _auth(client, 8004)
    await _set_checkin_state(db_session, 8004, _today() - timedelta(days=2), streak_count=5, streak_freezes=1)

    r = await client.post("/api/v1/checkin", headers=headers)
    body = r.json()
    assert body["streak_count"] == 6
    assert body["streak_freezes"] == 0  # consumed


async def test_checkin_gap_of_two_days_without_freeze_resets_streak(client, db_session):
    headers = await _auth(client, 8005)
    await _set_checkin_state(db_session, 8005, _today() - timedelta(days=2), streak_count=5, streak_freezes=0)

    r = await client.post("/api/v1/checkin", headers=headers)
    assert r.json()["streak_count"] == 1


async def test_seventh_day_streak_awards_bonus_xp(client, db_session):
    headers = await _auth(client, 8006)
    await _set_checkin_state(db_session, 8006, _today() - timedelta(days=1), streak_count=6)

    r = await client.post("/api/v1/checkin", headers=headers)
    body = r.json()
    assert body["streak_count"] == 7
    assert body["xp_awarded"] == 90  # 10 + 5*6 base + 50 bonus


async def test_get_checkin_status_matches_post_result(client, db_session):
    headers = await _auth(client, 8007)
    r1 = await client.get("/api/v1/checkin", headers=headers)
    assert r1.json()["checked_in_today"] is False

    await client.post("/api/v1/checkin", headers=headers)

    r2 = await client.get("/api/v1/checkin", headers=headers)
    assert r2.json()["checked_in_today"] is True
