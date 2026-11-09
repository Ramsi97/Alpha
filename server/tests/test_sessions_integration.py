"""Integration tests: full HTTP flow through FastAPI against a real
Postgres (alphago_test) and a fresh fakeredis per test. Exercises the exact
sequence plan section 8.1 describes."""

import hashlib
import hmac
import json
import time
import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import pytest
from sqlalchemy import select, update

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

GAME_MINESWEEPER = dict(
    slug="minesweeper", version="1.0.0", title={"en": "Minesweeper"}, description={"en": "d"},
    category="logic", thumbnail_url="t.svg", entry_url="http://x/minesweeper/index.html",
    variants=["easy", "medium", "hard"], max_score=1500, min_play_seconds=8, max_score_per_second=50,
    xp_rate=0.08, max_xp_per_run=120, license_code="MIT", license_assets="none",
    author="a", source_url="http://x", size_kb=63, status="active",
)


def make_init_data(telegram_id: int, bot_token: str) -> str:
    user = json.dumps({"id": telegram_id, "first_name": f"P{telegram_id}", "language_code": "en"})
    pairs = {"auth_date": str(int(time.time())), "user": user}
    data_check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    pairs["hash"] = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    return urlencode(pairs)


async def _seed_game(db_session, **overrides):
    data = {**GAME_2048, **overrides}
    game = Game(**data)
    db_session.add(game)
    await db_session.commit()
    return game


async def _auth(client, telegram_id: int) -> dict:
    r = await client.post("/api/v1/auth/telegram", json={"init_data": make_init_data(telegram_id, settings.bot_token)})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _backdate(db_session, session_id, seconds):
    past = datetime.now(UTC) - timedelta(seconds=seconds)
    await db_session.execute(update(GameSession).where(GameSession.id == session_id).values(started_at=past))
    await db_session.commit()


async def test_happy_path_awards_correct_xp_and_rank(client, db_session):
    await _seed_game(db_session)
    headers = await _auth(client, 9001)

    r = await client.post("/api/v1/games/2048/sessions", json={}, headers=headers)
    assert r.status_code == 200
    sess = r.json()

    await _backdate(db_session, uuid.UUID(sess["session_id"]), 30)

    r = await client.post(
        f"/api/v1/sessions/{sess['session_id']}/finish",
        json={"token": sess["token"], "score": 20000}, headers=headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["xp_awarded"] == 200
    assert body["total_xp"] == 200
    assert body["level"] == 2
    assert body["rank"] == 1
    assert body["flagged"] is False


async def test_finish_before_min_play_seconds_is_rejected(client, db_session):
    await _seed_game(db_session)
    headers = await _auth(client, 9002)
    r = await client.post("/api/v1/games/2048/sessions", json={}, headers=headers)
    sess = r.json()
    r = await client.post(
        f"/api/v1/sessions/{sess['session_id']}/finish",
        json={"token": sess["token"], "score": 5000}, headers=headers,
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "rejected"


async def test_repeated_finish_is_idempotent(client, db_session):
    await _seed_game(db_session)
    headers = await _auth(client, 9003)
    r = await client.post("/api/v1/games/2048/sessions", json={}, headers=headers)
    sess = r.json()
    await _backdate(db_session, uuid.UUID(sess["session_id"]), 30)

    payload = {"token": sess["token"], "score": 20000}
    r1 = await client.post(f"/api/v1/sessions/{sess['session_id']}/finish", json=payload, headers=headers)
    r2 = await client.post(f"/api/v1/sessions/{sess['session_id']}/finish", json=payload, headers=headers)
    assert r1.json()["total_xp"] == r2.json()["total_xp"] == 200, "XP must not be awarded twice"


async def test_wrong_token_is_rejected(client, db_session):
    await _seed_game(db_session)
    headers = await _auth(client, 9004)
    r = await client.post("/api/v1/games/2048/sessions", json={}, headers=headers)
    sess = r.json()
    await _backdate(db_session, uuid.UUID(sess["session_id"]), 30)
    r = await client.post(
        f"/api/v1/sessions/{sess['session_id']}/finish",
        json={"token": "wrong-token-entirely", "score": 100}, headers=headers,
    )
    assert r.status_code == 401


async def test_implausible_score_is_flagged_and_earns_no_xp(client, db_session):
    await _seed_game(db_session)
    headers = await _auth(client, 9005)
    r = await client.post("/api/v1/games/2048/sessions", json={}, headers=headers)
    sess = r.json()
    await _backdate(db_session, uuid.UUID(sess["session_id"]), 20)  # exactly min_play_seconds
    r = await client.post(
        f"/api/v1/sessions/{sess['session_id']}/finish",
        json={"token": sess["token"], "score": 500000}, headers=headers,  # way over max_score_per_second
    )
    assert r.status_code == 200
    body = r.json()
    assert body["flagged"] is True
    assert body["xp_awarded"] == 0


async def test_flagged_score_does_not_leak_into_personal_best(client, db_session):
    await _seed_game(db_session)
    headers = await _auth(client, 9006)

    r = await client.post("/api/v1/games/2048/sessions", json={}, headers=headers)
    sess = r.json()
    await _backdate(db_session, uuid.UUID(sess["session_id"]), 30)
    r = await client.post(
        f"/api/v1/sessions/{sess['session_id']}/finish",
        json={"token": sess["token"], "score": 20000}, headers=headers,
    )
    assert r.json()["personal_best"] == 20000

    r = await client.post("/api/v1/games/2048/sessions", json={}, headers=headers)
    sess2 = r.json()
    await _backdate(db_session, uuid.UUID(sess2["session_id"]), 20)
    r = await client.post(
        f"/api/v1/sessions/{sess2['session_id']}/finish",
        json={"token": sess2["token"], "score": 500000}, headers=headers,
    )
    assert r.json()["flagged"] is True
    assert r.json()["personal_best"] == 20000, "a flagged run must not become the displayed personal best"


async def test_invalid_variant_rejected_at_session_creation(client, db_session):
    await _seed_game(db_session, **GAME_MINESWEEPER)
    headers = await _auth(client, 9007)
    r = await client.post("/api/v1/games/minesweeper/sessions", json={"variant": "impossible"}, headers=headers)
    assert r.status_code == 400


async def test_starting_new_session_expires_the_previous_active_one(client, db_session):
    await _seed_game(db_session)
    headers = await _auth(client, 9008)
    r1 = await client.post("/api/v1/games/2048/sessions", json={}, headers=headers)
    first_id = uuid.UUID(r1.json()["session_id"])

    r2 = await client.post("/api/v1/games/2048/sessions", json={}, headers=headers)
    assert r2.status_code == 200

    row = (await db_session.execute(select(GameSession).where(GameSession.id == first_id))).scalar_one()
    assert row.status == "expired"


async def test_leaderboard_ranks_multiple_players_correctly(client, db_session):
    await _seed_game(db_session)
    scores = {9101: 10000, 9102: 30000, 9103: 20000}
    headers_by_player = {}
    for telegram_id, score in scores.items():
        headers = await _auth(client, telegram_id)
        headers_by_player[telegram_id] = headers
        r = await client.post("/api/v1/games/2048/sessions", json={}, headers=headers)
        sess = r.json()
        await _backdate(db_session, uuid.UUID(sess["session_id"]), 30)
        await client.post(
            f"/api/v1/sessions/{sess['session_id']}/finish",
            json={"token": sess["token"], "score": score}, headers=headers,
        )

    r = await client.get("/api/v1/leaderboards/games/2048", headers=headers_by_player[9101])
    assert r.status_code == 200
    entries = r.json()["entries"]
    assert [e["score"] for e in entries] == [30000, 20000, 10000]
    assert r.json()["my_rank"] == 3  # 9101 scored lowest


async def test_session_rate_limit_enforced(client, db_session):
    await _seed_game(db_session)
    headers = await _auth(client, 9201)
    hit_429 = False
    for _ in range(65):
        r = await client.post("/api/v1/games/2048/sessions", json={}, headers=headers)
        if r.status_code == 429:
            hit_429 = True
            break
    assert hit_429, "expected to hit the 60/hour session-start rate limit"


async def test_session_start_per_ip_limit_catches_many_accounts_one_ip(client, db_session):
    """Plan section 17: per-user AND per-IP. Creates many distinct users
    directly (bypassing /auth/telegram's own rate limit, which would
    otherwise trigger first and make this indistinguishable from testing
    that endpoint instead) so each user's own per-user session_start
    counter (limit 60) never comes close to tripping, while the shared
    per-IP counter (limit 300) — all these requests share one IP under
    the test harness's ASGI transport — eventually does."""
    await _seed_game(db_session)

    from app.core.security import issue_jwt
    from app.services.auth import _random_referral_code
    from app.models.user import User as UserModel

    hit_429 = False
    for i in range(310):
        user = UserModel(
            telegram_id=900_000 + i, username=f"ipuser{i}", first_name="IP",
            language="en", referral_code=_random_referral_code(),
        )
        db_session.add(user)
        await db_session.flush()
        token, _ttl = issue_jwt(user.id, user.telegram_id)
        await db_session.commit()

        r = await client.post(
            "/api/v1/games/2048/sessions", json={}, headers={"Authorization": f"Bearer {token}"}
        )
        if r.status_code == 429:
            hit_429 = True
            break
    assert hit_429, "expected the per-IP session_start limit (300) to trigger across many distinct users"
