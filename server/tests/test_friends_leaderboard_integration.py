"""Integration tests for the friends leaderboard (plan section 15:
GET /leaderboards/friends) — built from the referral graph, not Redis."""

import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

from sqlalchemy import select, update as sa_update

from app.core.config import settings
from app.models.user import User


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


async def test_referred_friends_see_each_other_on_the_leaderboard(client, db_session):
    referrer_headers = await _auth(client, 9301)
    referrer = (
        await db_session.execute(select(User).where(User.telegram_id == 9301))
    ).scalar_one()

    friend_headers = await _auth(client, 9302, start_param=f"r_{referrer.referral_code}")

    stranger_headers = await _auth(client, 9303)

    await db_session.execute(sa_update(User).where(User.telegram_id == 9301).values(total_xp=100))
    await db_session.execute(sa_update(User).where(User.telegram_id == 9302).values(total_xp=50))
    await db_session.execute(sa_update(User).where(User.telegram_id == 9303).values(total_xp=999))
    await db_session.commit()

    r = await client.get("/api/v1/leaderboards/friends", headers=referrer_headers)
    assert r.status_code == 200
    body = r.json()
    ids_in_board = {e["user_id"] for e in body["entries"]}
    scores_by_id = {e["user_id"]: e["score"] for e in body["entries"]}

    friend = (await db_session.execute(select(User).where(User.telegram_id == 9302))).scalar_one()
    stranger = (await db_session.execute(select(User).where(User.telegram_id == 9303))).scalar_one()

    assert friend.id in ids_in_board
    assert stranger.id not in ids_in_board  # no referral/challenge connection
    assert scores_by_id[referrer.id] == 100
    assert scores_by_id[friend.id] == 50
    assert body["my_rank"] == 1
    assert body["my_score"] == 100


async def test_lone_user_sees_only_self(client, db_session):
    headers = await _auth(client, 9304)
    r = await client.get("/api/v1/leaderboards/friends", headers=headers)
    body = r.json()
    assert len(body["entries"]) == 1
    assert body["my_rank"] == 1
