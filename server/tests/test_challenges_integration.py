"""Integration tests for challenges (plan section 12.5)."""

import hashlib
import hmac
import json
import time
import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from sqlalchemy import select, update as sa_update

from app.core.config import settings
from app.models.challenge import Challenge, ChallengeBeat
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


async def test_create_and_fetch_challenge(client, db_session):
    db_session.add(Game(**GAME_2048))
    await db_session.commit()
    headers = await _auth(client, 8101)

    r = await client.post(
        "/api/v1/challenges", json={"game_slug": "2048", "score_to_beat": 5000}, headers=headers
    )
    assert r.status_code == 200
    body = r.json()
    assert body["score_to_beat"] == 5000
    assert body["share_link"].endswith(f"?startapp=c_{body['token']}")

    r2 = await client.get(f"/api/v1/challenges/{body['token']}", headers=headers)
    assert r2.status_code == 200
    assert r2.json()["token"] == body["token"]


async def test_beating_a_challenge_rewards_the_challenger(client, db_session):
    db_session.add(Game(**GAME_2048))
    await db_session.commit()
    challenger_headers = await _auth(client, 8102)
    friend_headers = await _auth(client, 8103)

    r = await client.post(
        "/api/v1/challenges", json={"game_slug": "2048", "score_to_beat": 5000}, headers=challenger_headers
    )
    token = r.json()["token"]

    result = await _play_and_finish(client, db_session, friend_headers, 6000)  # beats 5000
    assert result["flagged"] is False

    me_challenger = await client.get("/api/v1/me", headers=challenger_headers)
    assert me_challenger.json()["total_xp"] == 15  # default challenge_beat_xp

    row = (await db_session.execute(select(ChallengeBeat))).scalar_one()
    assert row.beater_id is not None  # a beat row exists


async def test_score_below_target_does_not_beat_challenge(client, db_session):
    db_session.add(Game(**GAME_2048))
    await db_session.commit()
    challenger_headers = await _auth(client, 8104)
    friend_headers = await _auth(client, 8105)

    await client.post(
        "/api/v1/challenges", json={"game_slug": "2048", "score_to_beat": 5000}, headers=challenger_headers
    )
    await _play_and_finish(client, db_session, friend_headers, 1000)  # below target

    me_challenger = await client.get("/api/v1/me", headers=challenger_headers)
    assert me_challenger.json()["total_xp"] == 0

    rows = (await db_session.execute(select(ChallengeBeat))).scalars().all()
    assert len(rows) == 0


async def test_same_beater_does_not_reward_challenger_twice(client, db_session):
    db_session.add(Game(**GAME_2048))
    await db_session.commit()
    challenger_headers = await _auth(client, 8106)
    friend_headers = await _auth(client, 8107)

    await client.post(
        "/api/v1/challenges", json={"game_slug": "2048", "score_to_beat": 5000}, headers=challenger_headers
    )
    await _play_and_finish(client, db_session, friend_headers, 6000)
    await _play_and_finish(client, db_session, friend_headers, 7000)  # beats it again

    me_challenger = await client.get("/api/v1/me", headers=challenger_headers)
    assert me_challenger.json()["total_xp"] == 15  # only rewarded once


async def test_multiple_different_friends_each_reward_the_challenger(client, db_session):
    db_session.add(Game(**GAME_2048))
    await db_session.commit()
    challenger_headers = await _auth(client, 8108)
    friend1_headers = await _auth(client, 8109)
    friend2_headers = await _auth(client, 8110)

    await client.post(
        "/api/v1/challenges", json={"game_slug": "2048", "score_to_beat": 5000}, headers=challenger_headers
    )
    await _play_and_finish(client, db_session, friend1_headers, 6000)
    await _play_and_finish(client, db_session, friend2_headers, 6000)

    me_challenger = await client.get("/api/v1/me", headers=challenger_headers)
    assert me_challenger.json()["total_xp"] == 30  # rewarded for each distinct beater


async def test_challenger_cannot_beat_their_own_challenge(client, db_session):
    db_session.add(Game(**GAME_2048))
    await db_session.commit()
    challenger_headers = await _auth(client, 8111)

    await client.post(
        "/api/v1/challenges", json={"game_slug": "2048", "score_to_beat": 5000}, headers=challenger_headers
    )
    await _play_and_finish(client, db_session, challenger_headers, 6000)

    me = await client.get("/api/v1/me", headers=challenger_headers)
    run_xp = int(6000 * 0.01)
    assert me.json()["total_xp"] == run_xp  # no extra challenge-beat XP for self


async def test_flagged_run_does_not_beat_challenge(client, db_session):
    db_session.add(Game(**GAME_2048))
    await db_session.commit()
    challenger_headers = await _auth(client, 8112)
    friend_headers = await _auth(client, 8113)

    await client.post(
        "/api/v1/challenges", json={"game_slug": "2048", "score_to_beat": 5000}, headers=challenger_headers
    )

    r = await client.post("/api/v1/games/2048/sessions", json={}, headers=friend_headers)
    sess = r.json()
    past = datetime.now(UTC) - timedelta(seconds=20)
    await db_session.execute(
        sa_update(GameSession).where(GameSession.id == uuid.UUID(sess["session_id"])).values(started_at=past)
    )
    await db_session.commit()
    result = await client.post(
        f"/api/v1/sessions/{sess['session_id']}/finish",
        json={"token": sess["token"], "score": 500000}, headers=friend_headers,  # flagged
    )
    assert result.json()["flagged"] is True

    me_challenger = await client.get("/api/v1/me", headers=challenger_headers)
    assert me_challenger.json()["total_xp"] == 0
