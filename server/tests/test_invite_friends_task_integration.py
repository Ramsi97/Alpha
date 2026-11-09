"""Integration test for the invite_friends task handler (plan section 12.2),
which now counts *rewarded* referrals (plan section 12.4, built in B4),
not just signups — a referred friend who never plays shouldn't satisfy it."""

import hashlib
import hmac
import json
import time
import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from sqlalchemy import select, update as sa_update

from app.core.config import settings
from app.models.game import Game
from app.models.session import GameSession
from app.models.task import Task
from app.models.user import User

GAME_2048 = dict(
    slug="2048", version="1.0.0", title={"en": "2048"}, description={"en": "d"},
    category="number-puzzle", thumbnail_url="t.svg", entry_url="http://x/2048/index.html",
    variants=[], max_score=500000, min_play_seconds=20, max_score_per_second=1000,
    xp_rate=0.01, max_xp_per_run=300, license_code="MIT", license_assets="none",
    author="a", source_url="http://x", size_kb=136, status="active",
)


def make_init_data(telegram_id: int, start_param: str | None = None) -> str:
    user = json.dumps({"id": telegram_id, "first_name": f"P{telegram_id}", "language_code": "en"})
    pairs = {"auth_date": str(int(time.time())), "user": user}
    if start_param:
        pairs["start_param"] = start_param
    data_check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", settings.bot_token.encode(), hashlib.sha256).digest()
    pairs["hash"] = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    return urlencode(pairs)


async def _auth(client, telegram_id: int, start_param: str | None = None) -> dict:
    r = await client.post("/api/v1/auth/telegram", json={"init_data": make_init_data(telegram_id, start_param)})
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


async def test_invite_friends_requires_an_activated_referral_not_just_a_signup(client, db_session):
    db_session.add(Game(**GAME_2048))
    task = Task(
        type="invite_friends", title={"en": "t"}, description={"en": "d"}, payload={"min_referrals": 1},
        xp_reward=10, period="once", verify_method="auto", active=True,
    )
    db_session.add(task)
    await db_session.commit()

    referrer_headers = await _auth(client, 9401)
    referrer = (await db_session.execute(select(User).where(User.telegram_id == 9401))).scalar_one()

    r = await client.post(f"/api/v1/tasks/{task.id}/start", headers=referrer_headers)
    assert r.status_code == 200, r.text

    # Friend signs up under the referrer's code but hasn't played yet —
    # the referral exists but is still 'pending', not 'rewarded'.
    friend_headers = await _auth(client, 9402, start_param=f"r_{referrer.referral_code}")

    r = await client.post(f"/api/v1/tasks/{task.id}/verify", headers=referrer_headers)
    assert r.json()["status"] == "started"  # not met yet

    # Now the friend actually plays a valid run, activating the referral.
    await _play_and_finish(client, db_session, friend_headers, 6000)

    r = await client.post(f"/api/v1/tasks/{task.id}/verify", headers=referrer_headers)
    assert r.json()["status"] == "completed"
