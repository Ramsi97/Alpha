"""Load test (plan section 18/21/B6: "Load test (k6 or Locust) at several
times expected peak; fix bottlenecks").

Targets the traffic mix plan section 20 estimates for 100k users / 10k
DAU: mostly catalog/leaderboard/profile reads, with score submissions a
small minority (~1-2/s average, 20-30/s at peak, out of 50-100 req/s
overall peak). Weights below mirror that read-heavy mix.

Usage (against a locally running `uvicorn app.main:app`):
    pip install locust
    locust -f scripts/locustfile.py --host http://localhost:8000 --headless -u 50 -r 10 -t 60s

Each simulated user picks a pre-minted JWT from
scripts/seed_load_test_users.py's output (/tmp/load_test_tokens.json) —
run that script first. Going through POST /auth/telegram per simulated
user instead would immediately trip its own per-IP rate limit (30/hour)
since a load generator is, by definition, one IP; real traffic at the
volumes plan section 20 describes is dominated by already-authenticated
reads using a token across its whole TTL, not repeated fresh logins, so
this is also the more realistic shape for what this test is measuring.

The score-submission task directly nudges its own session's started_at
back in the database (same technique tests/test_sessions_integration.py
uses) instead of literally sleeping min_play_seconds per iteration —
otherwise each simulated user could only ever generate one score
submission every 20+ seconds, which would throttle the load test itself
rather than the server. Needs PG_DSN (plain libpq, not +asyncpg) pointed
at the same database the server uses.
"""

import asyncio
import itertools
import json
import os
import random
import uuid
from datetime import UTC, datetime, timedelta

import asyncpg
from locust import HttpUser, between, task

PG_DSN = os.environ.get("PG_DSN", "postgresql://ramsi@/alphago_dev")
GAME_SLUG = os.environ.get("LOAD_TEST_GAME_SLUG", "2048")
TOKENS_FILE = os.environ.get("LOAD_TEST_TOKENS_FILE", "/tmp/load_test_tokens.json")

with open(TOKENS_FILE) as f:
    _TOKENS = itertools.cycle(json.load(f))


async def _rewind_session_start(session_id: str) -> None:
    conn = await asyncpg.connect(PG_DSN)
    try:
        await conn.execute(
            "UPDATE game_sessions SET started_at = $1 WHERE id = $2",
            datetime.now(UTC) - timedelta(seconds=30),
            uuid.UUID(session_id),
        )
    finally:
        await conn.close()


class PlayerUser(HttpUser):
    wait_time = between(0.5, 2.0)

    def on_start(self):
        self.headers = {"Authorization": f"Bearer {next(_TOKENS)}"}

    @task(5)
    def browse_catalog(self):
        self.client.get("/api/v1/games", headers=self.headers)

    @task(3)
    def read_xp_leaderboard(self):
        self.client.get("/api/v1/leaderboards/xp", headers=self.headers)

    @task(2)
    def read_game_leaderboard(self):
        self.client.get(f"/api/v1/leaderboards/games/{GAME_SLUG}", headers=self.headers)

    @task(2)
    def read_profile(self):
        self.client.get("/api/v1/me", headers=self.headers)

    @task(2)
    def checkin(self):
        self.client.post("/api/v1/checkin", headers=self.headers)

    @task(1)
    def submit_score(self):
        r = self.client.post(f"/api/v1/games/{GAME_SLUG}/sessions", json={}, headers=self.headers)
        if r.status_code != 200:
            return
        session_id = r.json()["session_id"]
        token = r.json()["token"]
        asyncio.run(_rewind_session_start(session_id))
        self.client.post(
            f"/api/v1/sessions/{session_id}/finish",
            json={"token": token, "score": random.randint(100, 4000)},
            headers=self.headers,
        )
