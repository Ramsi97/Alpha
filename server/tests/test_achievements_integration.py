"""Integration tests for achievement unlocking, fired from both
finish_session (score_submitted) and do_checkin (checked_in)."""

import hashlib
import hmac
import json
import time
import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from sqlalchemy import update as sa_update

from app.core.config import settings
from app.models.achievement import Achievement
from app.models.game import Game
from app.models.session import GameSession
from app.models.user import User

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


async def _seed_game(db_session, **overrides):
    db_session.add(Game(**{**GAME_2048, **overrides}))
    await db_session.commit()


async def _seed_achievement(db_session, key, condition, xp_reward=0, title=None):
    db_session.add(Achievement(
        key=key, title=title or {"en": key}, description={"en": key}, icon="x",
        condition=condition, xp_reward=xp_reward,
    ))
    await db_session.commit()


async def _backdate(db_session, session_id, seconds):
    past = datetime.now(UTC) - timedelta(seconds=seconds)
    await db_session.execute(sa_update(GameSession).where(GameSession.id == session_id).values(started_at=past))
    await db_session.commit()


async def test_total_runs_achievement_unlocks_on_first_finish(client, db_session):
    await _seed_game(db_session)
    await _seed_achievement(db_session, "first_run", {"type": "total_runs", "value": 1}, xp_reward=20)
    headers = await _auth(client, 8101)

    r = await client.post("/api/v1/games/2048/sessions", json={}, headers=headers)
    sess = r.json()
    await _backdate(db_session, uuid.UUID(sess["session_id"]), 30)
    r = await client.post(
        f"/api/v1/sessions/{sess['session_id']}/finish",
        json={"token": sess["token"], "score": 20000}, headers=headers,
    )
    body = r.json()
    assert "first_run" in body["new_achievements"]
    assert body["total_xp"] == 200 + 20  # run XP + achievement XP


async def test_achievement_does_not_unlock_twice(client, db_session):
    await _seed_game(db_session)
    await _seed_achievement(db_session, "first_run", {"type": "total_runs", "value": 1}, xp_reward=20)
    headers = await _auth(client, 8102)

    for _ in range(2):
        r = await client.post("/api/v1/games/2048/sessions", json={}, headers=headers)
        sess = r.json()
        await _backdate(db_session, uuid.UUID(sess["session_id"]), 30)
        r = await client.post(
            f"/api/v1/sessions/{sess['session_id']}/finish",
            json={"token": sess["token"], "score": 20000}, headers=headers,
        )

    # Second run: total_runs condition (value=1) is still met, but it's
    # already unlocked — must not appear again or award XP twice.
    assert "first_run" not in r.json()["new_achievements"]
    assert r.json()["total_xp"] == 400 + 20  # 2 runs * 200 xp + exactly one achievement award


async def test_score_at_least_achievement_ignores_flagged_scores(client, db_session):
    await _seed_game(db_session)
    await _seed_achievement(db_session, "score_5000", {"type": "score_at_least", "game": "2048", "value": 5000})
    headers = await _auth(client, 8103)

    r = await client.post("/api/v1/games/2048/sessions", json={}, headers=headers)
    sess = r.json()
    await _backdate(db_session, uuid.UUID(sess["session_id"]), 20)  # min_play_seconds, for a flagged ratio
    r = await client.post(
        f"/api/v1/sessions/{sess['session_id']}/finish",
        json={"token": sess["token"], "score": 500000}, headers=headers,  # flagged: way over max_score_per_second
    )
    assert r.json()["flagged"] is True
    assert "score_5000" not in r.json()["new_achievements"], "a flagged score must not unlock a score achievement"


async def test_score_at_least_achievement_unlocks_on_legitimate_score(client, db_session):
    await _seed_game(db_session)
    await _seed_achievement(db_session, "score_5000", {"type": "score_at_least", "game": "2048", "value": 5000})
    headers = await _auth(client, 8104)

    r = await client.post("/api/v1/games/2048/sessions", json={}, headers=headers)
    sess = r.json()
    await _backdate(db_session, uuid.UUID(sess["session_id"]), 30)
    r = await client.post(
        f"/api/v1/sessions/{sess['session_id']}/finish",
        json={"token": sess["token"], "score": 20000}, headers=headers,
    )
    assert "score_5000" in r.json()["new_achievements"]


async def test_streak_achievement_unlocks_via_checkin(client, db_session):
    await _seed_achievement(db_session, "streak_3", {"type": "streak", "value": 3}, xp_reward=15)
    headers = await _auth(client, 8105)

    await db_session.execute(
        sa_update(User).where(User.telegram_id == 8105)
        .values(last_checkin_date=datetime.now(UTC).date() - timedelta(days=1), streak_count=2)
    )
    await db_session.commit()

    r = await client.post("/api/v1/checkin", headers=headers)
    body = r.json()
    assert body["streak_count"] == 3
    assert "streak_3" in body["new_achievements"]


async def test_level_achievement_unlocks_from_game_xp(client, db_session):
    await _seed_game(db_session)
    await _seed_achievement(db_session, "level_2", {"type": "level", "value": 2}, xp_reward=0)
    headers = await _auth(client, 8106)

    r = await client.post("/api/v1/games/2048/sessions", json={}, headers=headers)
    sess = r.json()
    await _backdate(db_session, uuid.UUID(sess["session_id"]), 30)
    r = await client.post(
        f"/api/v1/sessions/{sess['session_id']}/finish",
        json={"token": sess["token"], "score": 20000}, headers=headers,  # 200 xp -> level 2
    )
    assert r.json()["level"] == 2
    assert "level_2" in r.json()["new_achievements"]
