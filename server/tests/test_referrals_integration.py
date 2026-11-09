"""Integration tests for referrals (plan section 12.4): creation on
signup, activation on first valid run, and the referrer's daily/total caps."""

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
from app.models.referral import Referral
from app.models.session import GameSession
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


async def _auth(client, telegram_id: int, start_param: str | None = None) -> tuple[dict, dict]:
    r = await client.post("/api/v1/auth/telegram", json={"init_data": make_init_data(telegram_id, start_param)})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}, r.json()["user"]


async def _play_and_finish(client, db_session, headers, score: int, telegram_id_for_sess: int | None = None) -> dict:
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


async def test_referral_link_shape_and_initial_counts(client, db_session):
    headers, _user = await _auth(client, 8001)
    r = await client.get("/api/v1/referrals", headers=headers)
    body = r.json()
    assert body["referral_link"].endswith(f"?startapp=r_{body['referral_code']}")
    assert body["pending_count"] == 0
    assert body["rewarded_count"] == 0


async def test_signup_with_referral_code_creates_pending_referral(client, db_session):
    _referrer_headers, referrer = await _auth(client, 8002)
    await _auth(client, 8003, start_param=f"r_{referrer['referral_code']}")

    row = (await db_session.execute(select(Referral).where(Referral.referrer_id == referrer["id"]))).scalar_one()
    assert row.status == "pending"


async def test_referral_activates_on_first_valid_run_and_rewards_both_sides(client, db_session):
    db_session.add(Game(**GAME_2048))
    await db_session.commit()

    referrer_headers, referrer = await _auth(client, 8004)
    referred_headers, _referred = await _auth(client, 8005, start_param=f"r_{referrer['referral_code']}")

    result = await _play_and_finish(client, db_session, referred_headers, 1000)
    assert result["flagged"] is False

    # Referred side got the welcome bonus on top of run XP.
    me_referred = await client.get("/api/v1/me", headers=referred_headers)
    run_xp = 1000 * 0.01  # xp_rate
    assert me_referred.json()["total_xp"] == int(run_xp) + 25  # default referral_xp_referred

    # Referrer got their reward too, with no run of their own.
    me_referrer = await client.get("/api/v1/me", headers=referrer_headers)
    assert me_referrer.json()["total_xp"] == 50  # default referral_xp_referrer

    row = (await db_session.execute(select(Referral).where(Referral.referrer_id == referrer["id"]))).scalar_one()
    assert row.status == "rewarded"
    assert row.rewarded_at is not None

    r = await client.get("/api/v1/referrals", headers=referrer_headers)
    assert r.json()["rewarded_count"] == 1
    assert r.json()["pending_count"] == 0


async def test_referral_does_not_activate_on_a_flagged_first_run(client, db_session):
    db_session.add(Game(**GAME_2048))
    await db_session.commit()
    referrer_headers, referrer = await _auth(client, 8006)
    referred_headers, _referred = await _auth(client, 8007, start_param=f"r_{referrer['referral_code']}")

    # A flagged (implausible) first run must not activate the referral.
    r = await client.post("/api/v1/games/2048/sessions", json={}, headers=referred_headers)
    sess = r.json()
    past = datetime.now(UTC) - timedelta(seconds=20)  # exactly min_play_seconds
    await db_session.execute(
        sa_update(GameSession).where(GameSession.id == uuid.UUID(sess["session_id"])).values(started_at=past)
    )
    await db_session.commit()
    result = await client.post(
        f"/api/v1/sessions/{sess['session_id']}/finish",
        json={"token": sess["token"], "score": 500000}, headers=referred_headers,  # flagged
    )
    assert result.json()["flagged"] is True

    row = (await db_session.execute(select(Referral).where(Referral.referrer_id == referrer["id"]))).scalar_one()
    assert row.status == "pending"  # still pending — flagged run didn't activate it

    # Now a real, valid run does activate it.
    result2 = await _play_and_finish(client, db_session, referred_headers, 1000)
    assert result2["flagged"] is False
    await db_session.refresh(row)
    assert row.status == "rewarded"


async def test_referrer_daily_cap_withholds_referrer_reward_but_still_activates(client, db_session, monkeypatch):
    db_session.add(Game(**GAME_2048))
    await db_session.commit()
    referrer_headers, referrer = await _auth(client, 8010)

    # Set the daily cap to 1 via the settings table directly (simplest in a test).
    from app.models.setting import Setting
    db_session.add(Setting(key="referral_daily_cap", value=1))
    await db_session.commit()

    # First referred friend: activates normally, referrer gets rewarded (count -> 1, at cap).
    referred1_headers, _r1 = await _auth(client, 8011, start_param=f"r_{referrer['referral_code']}")
    await _play_and_finish(client, db_session, referred1_headers, 1000)
    me1 = await client.get("/api/v1/me", headers=referrer_headers)
    assert me1.json()["total_xp"] == 50

    # Second referred friend same day: referral still activates (referred
    # side gets their bonus), but referrer is at the daily cap already.
    referred2_headers, _r2 = await _auth(client, 8012, start_param=f"r_{referrer['referral_code']}")
    result = await _play_and_finish(client, db_session, referred2_headers, 1000)
    assert result["flagged"] is False

    row2 = (
        await db_session.execute(select(Referral).where(Referral.referred_id == _r2["id"]))
    ).scalar_one()
    assert row2.status == "rewarded"  # activated...

    me2 = await client.get("/api/v1/me", headers=referrer_headers)
    assert me2.json()["total_xp"] == 50  # ...but referrer's XP did NOT increase again (capped)

    me_referred2 = await client.get("/api/v1/me", headers=referred2_headers)
    run_xp = 1000 * 0.01
    assert me_referred2.json()["total_xp"] == int(run_xp) + 25  # referred side still got their bonus
