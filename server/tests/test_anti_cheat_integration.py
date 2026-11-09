"""Integration tests for the statistical-outlier anti-cheat check (plan
section 17) — independent of the existing max_score_per_second check."""

import hashlib
import hmac
import json
import time
import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from sqlalchemy import update as sa_update

from app.core.config import settings
from app.models.game import Game
from app.models.session import GameSession

# A game with a very generous max_score_per_second, so the time-based
# check never fires — isolates the statistical check for testing.
GAME = dict(
    slug="statcheck", version="1.0.0", title={"en": "t"}, description={"en": "d"},
    category="arcade", thumbnail_url="t.svg", entry_url="http://x/statcheck/index.html",
    variants=[], max_score=1_000_000, min_play_seconds=5, max_score_per_second=1_000_000,
    xp_rate=0.01, max_xp_per_run=300, license_code="MIT", license_assets="none",
    author="a", source_url="http://x", size_kb=10, status="active",
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


async def _play(client, db_session, headers, score: int) -> dict:
    r = await client.post("/api/v1/games/statcheck/sessions", json={}, headers=headers)
    sess = r.json()
    past = datetime.now(UTC) - timedelta(seconds=10)
    await db_session.execute(
        sa_update(GameSession).where(GameSession.id == uuid.UUID(sess["session_id"])).values(started_at=past)
    )
    await db_session.commit()
    r2 = await client.post(
        f"/api/v1/sessions/{sess['session_id']}/finish",
        json={"token": sess["token"], "score": score}, headers=headers,
    )
    return r2.json()


async def test_outlier_check_is_inactive_below_minimum_sample_size(client, db_session):
    db_session.add(Game(**GAME))
    await db_session.commit()
    headers = await _auth(client, 7601)

    # Fewer than MIN_SAMPLE_FOR_PERCENTILE_CHECK (20) runs exist — even a
    # huge score must not be flagged by the statistical check yet.
    for i in range(5):
        h = await _auth(client, 7610 + i)
        result = await _play(client, db_session, h, 100)
        assert result["flagged"] is False

    result = await _play(client, db_session, headers, 1_000_000)
    assert result["flagged"] is False


async def test_outlier_far_above_p99_gets_flagged(client, db_session):
    db_session.add(Game(**GAME))
    await db_session.commit()

    # Build a real distribution: 25 legitimate-looking runs clustered
    # around 100-200 points.
    for i in range(25):
        h = await _auth(client, 7700 + i)
        result = await _play(client, db_session, h, 100 + i * 4)  # 100..196
        assert result["flagged"] is False

    outlier_headers = await _auth(client, 7799)
    result = await _play(client, db_session, outlier_headers, 50_000)  # wildly above the cluster
    assert result["flagged"] is True
    assert result["xp_awarded"] == 0


async def test_score_within_normal_range_not_flagged_once_distribution_exists(client, db_session):
    db_session.add(Game(**GAME))
    await db_session.commit()

    for i in range(25):
        h = await _auth(client, 7800 + i)
        await _play(client, db_session, h, 100 + i * 4)

    normal_headers = await _auth(client, 7899)
    result = await _play(client, db_session, normal_headers, 190)  # within the existing cluster
    assert result["flagged"] is False
