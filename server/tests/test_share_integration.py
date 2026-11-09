"""Integration tests for score-card sharing (plan section 15: POST /share/score-card)."""

import hashlib
import hmac
import json
import time
from pathlib import Path
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


async def test_score_card_generates_and_serves_an_image(client, db_session):
    db_session.add(Game(**GAME_2048))
    await db_session.commit()
    headers = await _auth(client, 9201)

    r = await client.post(
        "/api/v1/share/score-card", json={"game_slug": "2048", "score": 12345}, headers=headers
    )
    assert r.status_code == 200, r.text
    url = r.json()["url"]
    assert url.startswith(f"{settings.public_base_url}/media/score_cards/")

    rel = url[len(settings.public_base_url):]
    file_path = Path(settings.media_dir) / rel.removeprefix("/media/")
    assert file_path.exists()
    assert file_path.stat().st_size > 0


async def test_score_card_is_cached_by_content(client, db_session):
    db_session.add(Game(**GAME_2048))
    await db_session.commit()
    headers = await _auth(client, 9202)

    r1 = await client.post(
        "/api/v1/share/score-card", json={"game_slug": "2048", "score": 500}, headers=headers
    )
    r2 = await client.post(
        "/api/v1/share/score-card", json={"game_slug": "2048", "score": 500}, headers=headers
    )
    assert r1.json()["url"] == r2.json()["url"]

    r3 = await client.post(
        "/api/v1/share/score-card", json={"game_slug": "2048", "score": 999}, headers=headers
    )
    assert r3.json()["url"] != r1.json()["url"]


async def test_score_card_unknown_game_404(client, db_session):
    headers = await _auth(client, 9203)
    r = await client.post(
        "/api/v1/share/score-card", json={"game_slug": "does-not-exist", "score": 1}, headers=headers
    )
    assert r.status_code == 404
