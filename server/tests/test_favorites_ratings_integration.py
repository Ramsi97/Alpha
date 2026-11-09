"""Integration tests for favorites, ratings, categories, trending (plan sections 7, 15)."""

import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

from app.core.config import settings
from app.models.game import Game

GAME_2048 = dict(
    slug="2048", version="1.0.0", title={"en": "2048"}, description={"en": "d"},
    category="number-puzzle", thumbnail_url="t.svg", entry_url="http://x/2048/index.html",
    variants=[], max_score=500000, min_play_seconds=20, max_score_per_second=1000,
    xp_rate=0.01, max_xp_per_run=300, license_code="MIT", license_assets="none",
    author="a", source_url="http://x", size_kb=136, status="active",
)
GAME_SNAKE = dict(
    slug="snake", version="1.0.0", title={"en": "Snake"}, description={"en": "d"},
    category="arcade", thumbnail_url="t.svg", entry_url="http://x/snake/index.html",
    variants=[], max_score=50000, min_play_seconds=10, max_score_per_second=500,
    xp_rate=0.02, max_xp_per_run=200, license_code="MIT", license_assets="none",
    author="a", source_url="http://x", size_kb=90, status="active",
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


async def test_favorite_toggle(client, db_session):
    db_session.add(Game(**GAME_2048))
    await db_session.commit()
    headers = await _auth(client, 9001)

    games = (await client.get("/api/v1/games", headers=headers)).json()
    assert games[0]["is_favorite"] is False

    r = await client.post("/api/v1/games/2048/favorite", headers=headers)
    assert r.status_code == 204

    games = (await client.get("/api/v1/games", headers=headers)).json()
    assert games[0]["is_favorite"] is True

    r = await client.delete("/api/v1/games/2048/favorite", headers=headers)
    assert r.status_code == 204

    games = (await client.get("/api/v1/games", headers=headers)).json()
    assert games[0]["is_favorite"] is False


async def test_rating_and_average(client, db_session):
    db_session.add(Game(**GAME_2048))
    await db_session.commit()
    headers1 = await _auth(client, 9002)
    headers2 = await _auth(client, 9003)

    r = await client.post("/api/v1/games/2048/rating", json={"rating": 5}, headers=headers1)
    assert r.status_code == 204
    await client.post("/api/v1/games/2048/rating", json={"rating": 3}, headers=headers2)

    games = (await client.get("/api/v1/games", headers=headers1)).json()
    assert games[0]["average_rating"] == 4.0

    # Re-rating replaces, doesn't add a second row.
    await client.post("/api/v1/games/2048/rating", json={"rating": 1}, headers=headers1)
    games = (await client.get("/api/v1/games", headers=headers1)).json()
    assert games[0]["average_rating"] == 2.0


async def test_rating_out_of_range_rejected(client, db_session):
    db_session.add(Game(**GAME_2048))
    await db_session.commit()
    headers = await _auth(client, 9004)
    r = await client.post("/api/v1/games/2048/rating", json={"rating": 6}, headers=headers)
    assert r.status_code == 422


async def test_category_filter(client, db_session):
    db_session.add(Game(**GAME_2048))
    db_session.add(Game(**GAME_SNAKE))
    await db_session.commit()
    headers = await _auth(client, 9005)

    r = await client.get("/api/v1/games", params={"category": "arcade"}, headers=headers)
    slugs = [g["slug"] for g in r.json()]
    assert slugs == ["snake"]


async def test_trending_sort(client, db_session):
    db_session.add(Game(**GAME_2048))
    db_session.add(Game(**{**GAME_SNAKE, "trending_score": 50}))
    await db_session.commit()
    headers = await _auth(client, 9006)

    r = await client.get("/api/v1/games", params={"sort_by": "trending"}, headers=headers)
    slugs = [g["slug"] for g in r.json()]
    assert slugs == ["snake", "2048"]
