# server/

AlphaGo backend (Phases B0-B6 of `../02-backend-plan.md`). FastAPI + SQLAlchemy (async) + PostgreSQL + Redis.

## What's here

- `app/core/` — config, DB engine (now with a configurable connection pool — see the load-test section), Redis client, JWT/`initData` validation, structured logging, error shape (now logs unhandled exceptions instead of silently swallowing them), rate limiting (per-user and per-IP), a Telegram Bot API client (real + fake-for-tests).
- `app/models/` — SQLAlchemy models for `users` (now with `deleted_at`), `games`, `game_sessions`, `scores`, `xp_events`, `settings`, `achievements`, `user_achievements`, `admin_users`, `audit_log`, `tasks`, `user_tasks`, `notification_outbox`, `referrals`, `challenges`, `challenge_beats`, `favorites`, `game_ratings`, `seasons`, `season_results`, `tournaments`, `tournament_entries`, `sponsors`.
- `app/schemas/` — Pydantic request/response models.
- `app/api/v1/` — routers: `auth`, `me` (now with `DELETE /me`), `games`, `sessions`, `leaderboards`, `checkin`, `achievements`, `tasks`, `admin`, `referrals`, `challenges`, `share`, `seasons` (admin), `tournaments` (public + admin), `analytics` (admin).
- `app/services/` — business logic: auth/user creation + admin bootstrap (now also reverses account deletion on a fresh real login), manifest import, session lifecycle + the finish-validation transaction (triggers referral activation, challenge-beat checks, and tournament scoring after a valid run), XP formula, leaderboards (Redis-backed global/per-game, Postgres-backed friends and season), check-in/streaks, achievement evaluator, the task engine, the notification outbox/worker, profile assembly, settings reader, audit logging, referrals, friend duels (challenges), favorites/ratings, the friends-graph lookup, score-card image generation, seasons, tournaments, account deletion.
- `app/workers/import_manifests.py` — the manifest import job (plan section 7), run manually for now.
- `app/workers/seed_achievements.py` — seeds the first 10 achievements (plan section 11), idempotent, run manually.
- `app/workers/notification_worker.py` — polls the notification outbox once a second; see "Notifications" below for why this isn't ARQ.
- `app/workers/update_trending.py` — recomputes `games.trending_score` from the last 3 days of finished sessions; idempotent, run on a schedule (e.g. hourly cron).
- `app/workers/end_season.py` / `app/workers/close_tournaments.py` — close any season/tournament whose `ends_at` has passed; idempotent, run on a schedule (e.g. hourly cron).
- `app/workers/rotate_daily_challenges.py` — gives any `play_game` task marked `payload.rotates: true` a fresh game+target once per its period (daily/weekly); idempotent per period, run on a schedule.
- `scripts/backup.sh` / `scripts/restore.sh` — Postgres backup and restore (plan section 19/B6).
- `scripts/locustfile.py` / `scripts/seed_load_test_users.py` — the load test (plan section 18/21/B6).
- `migrations/` — Alembic, async template.
- `../.github/workflows/backend-ci.yml` — CI: lint, migrate, test against a real Postgres service container (plan section 19/B6).
- `../PRIVACY.md` / `../TERMS.md` — draft privacy notice and terms (plan section 18/B6; **not legal advice**, need a real review before publishing).
- `tests/` — unit tests (`test_security.py`, `test_xp.py`, `test_i18n_notifications.py`, `test_startup_secrets.py`) and full HTTP integration suites for sessions, check-in, achievements, profile, tasks, admin (B2 + B3), the anti-cheat statistical check, referrals, challenges, favorites/ratings/categories/trending, score cards, the friends leaderboard (B4), seasons, tournaments, sponsors, analytics (B5), HTTP-level security checks, and account deletion (B6).

## Running locally (no Docker — see "About Docker" below)

This was built and tested entirely with a local Python venv against a **real local PostgreSQL** (not a container). No real Redis exists in this setup; `REDIS_URL=fakeredis://` (the default) makes `app/core/redis.py` fall back to an in-memory, protocol-compatible substitute — see that file's docstring. Point `REDIS_URL` at a real `redis://...` anywhere Redis is actually available.

```bash
cd server
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# One-time: create a local Postgres role/db if you don't have one.
# This environment used the existing OS user's peer-auth role via unix socket:
#   createdb alphago_dev
# DATABASE_URL in app/core/config.py defaults to postgresql+asyncpg://ramsi@/alphago_dev —
# change the username or set DATABASE_URL explicitly for a different setup.

alembic upgrade head
python -m app.workers.import_manifests          # imports every games/<slug>/game.json (status: pending)
python -m app.workers.seed_achievements         # seeds the first 10 achievements
uvicorn app.main:app --reload                   # http://localhost:8000/docs

# In a separate process once there's real notification traffic to send:
python -m app.workers.notification_worker

# On a schedule (e.g. hourly cron) once there's real play traffic:
python -m app.workers.update_trending
python -m app.workers.end_season
python -m app.workers.close_tournaments
python -m app.workers.rotate_daily_challenges
```

Newly-imported games start `pending` — an admin has to activate them (see "Admin access" below). Health checks: `GET /healthz` (process up), `GET /readyz` (DB + Redis reachable).

Score-card images (`POST /share/score-card`) render with Pillow and are cached on disk under `MEDIA_DIR` (default `./media`, gitignored), served back at `PUBLIC_BASE_URL/media/...` — set `PUBLIC_BASE_URL` to wherever this API is actually reachable from outside (not `localhost`) before real users share a card.

## Admin access

Set `ADMIN_TELEGRAM_IDS` (comma-separated Telegram user ids) in `.env`. The
first time that Telegram id calls `POST /auth/telegram`, it's automatically
granted an `admin_users` row (`app/services/auth.py:ensure_admin_bootstrap`)
— no separate admin-creation step, no UI (plan section 16 explicitly allows
API-only admin access for now — "the admin UI can start as a minimal web
page or even a protected set of bot commands; the API is the same"; no
frontend was requested for this backend-only pass).

- `GET`/`PATCH /admin/games/...` — review/activate games, tune `xp_rate`/caps.
- `GET`/`PUT /admin/settings/{key}` — tunables (`xp_run_thresholds`, `daily_game_xp_cap`).
- `GET`/`POST /admin/tasks`, `PATCH /admin/tasks/{id}` — task CRUD.
- `GET /admin/tasks/review-queue`, `POST /admin/user-tasks/{id}/approve|reject` — manual-verification tasks.
- `GET /admin/users?search=`, `POST /admin/users/{id}/ban|unban`, `POST /admin/users/{id}/adjust-xp` — user moderation; XP adjustments are ledger rows (plan section 9.3), never a direct balance edit.
- `GET /admin/flagged-scores`, `POST /admin/flagged-scores/{id}/approve|reject` — the anti-cheat hold queue.
- `POST /admin/notifications/process` — triggers one outbox-processing pass synchronously (for ops/testing; the real worker loop runs continuously).
- `GET`/`POST /admin/seasons`, `POST /admin/seasons/{id}/finalize` — season scheduling and manual finalize (B5).
- `POST /admin/tournaments`, `POST /admin/tournaments/{id}/close` — tournament scheduling and manual close (B5).
- `GET`/`POST /admin/sponsors`, `GET /admin/sponsors/{id}/report` — sponsor CRUD and a completions/XP report per sponsor (B5).
- `GET /admin/analytics/overview` — DAU, day-1 retention, runs per game (7 days), task completion rate, referral conversion (B5).

Every admin write lands in `audit_log` (`admin_id`, `action`, `target_type`/`target_id`, `details`).

## Tasks (plan section 12)

`GET /tasks`, `POST /tasks/{id}/start`, `POST /tasks/{id}/verify`. Handler types and their actual state:

| Type | Status |
|---|---|
| `play_game` | Fully working — checks real `scores` rows (min score/run count), excludes flagged runs. |
| `daily_open` | Fully working — defers to whatever `last_checkin_date` already says. |
| `open_link` / `share_story` | Fully working (`timed_claim`: just checks elapsed time since `start`). |
| `custom` | Fully working (`manual`: goes to `pending_review`, an admin approves/rejects). |
| `join_channel` | Handler implemented and unit-tested via `FakeTelegramClient`, but **unverified against the real Telegram API** — no bot token exists in this environment. Also: the plan calls for a throttled verification *queue*; this does a direct call instead. Fine at low volume, worth queuing before this sees real traffic. |
| `invite_friends` | Fully working as of B4 — counts *activated* referrals (`referrals.status == 'rewarded'`, i.e. the friend actually played a valid run), not just signups. |

## Notifications (plan section 14.3)

`app/services/notifications.py`'s `process_outbox()` implements every rule in plan 14.3 (skip disabled/blocked users, 429 → reschedule at `retry_after`, 403 → mark `bot_blocked` and skip, other errors → backoff then `failed` after 5 attempts) as a **plain polling function**, not an ARQ job. The plan recommends ARQ (Redis-backed), but ARQ's queue relies on Redis blocking-list semantics that `fakeredis` (the only Redis available in this environment — see above) doesn't reliably replicate. Wrapping `process_outbox()` in an actual ARQ cron job wherever real Redis exists is a small, low-risk change — the business logic doesn't need to move.

**Templates now cover `en`/`am`/`om`** (plan section 21: Afaan Oromo, Amharic, English) — `TEMPLATES` in that file, selected by `users.language` with a fallback to `en`. The Amharic and Afaan Oromo strings are a best-effort pass, not reviewed by a native speaker — they exercise the fallback/rendering mechanism correctly (see `tests/test_i18n_notifications.py`) but should get a native review before shipping to real users in either language. `PATCH /me`'s `language` field is now restricted to these three codes (`app/schemas/user.py`); `users.language` itself still accepts whatever Telegram's `language_code` says at signup, unrestricted.

Triggers wired end-to-end: **`level_up`** (`finish_session`/`do_checkin` on a level-up), **`friend_joined`** (referral activation), **`challenge_beaten`** (a friend duel beaten), **`season_end`** and **`tournament_end`** (both now pass `{"rank": ...}` — see the season/tournament close jobs below). **`new_task`** and **`tournament_start`** have templates ready but no producer yet (no broadcast-on-creation system built — see "What's NOT built yet").

## Anti-cheat (plan section 17)

Two independent flagging signals on every `finish`, either one holds the run (0 XP, kept out of leaderboards, visible in `GET /admin/flagged-scores`):
1. `score / duration > game.max_score_per_second` (B1, unchanged).
2. **New in B3**: `score > 2x` the 99th percentile of that game+variant's past non-flagged scores — but only once at least 20 such scores exist, so it's inert for a game's first players rather than flagging legitimate early plausible-ceiling runs.

Rate limiting is now both per-user and per-IP (`app/core/rate_limit.py`) on session start/finish and auth — catches "many accounts, one IP" abuse that a per-user-only limit can't.

## Referrals, challenges, favorites, score cards (B4, plan section 12.4/12.5/15)

- **Referrals**: `GET /referrals` returns the user's deep link (`?startapp=r_<code>`), pending count, rewarded count. Activation happens on the referred user's first-ever *valid* (non-flagged) run (`app/services/referrals.py:activate_referral_if_eligible`, called from `finish_session`) — the referred user's welcome bonus is unconditional, the referrer's reward respects a daily and total cap (activation still happens over-cap; only the reward is withheld).
- **Challenges**: `POST /challenges` creates a friend duel (`{game_slug, score_to_beat}` → token + expiry + share link); `GET /challenges/{token}` fetches one. Beating one on a valid, non-flagged run rewards the challenger once per distinct beater (`app/services/challenges.py:check_and_record_beats`). Duplicate-beat detection is a proactive query before insert (not insert-and-catch) specifically because a mid-transaction `rollback()` would expire the `user` ORM object `finish_session` keeps using afterward, crashing with `MissingGreenlet`; a `try/except IntegrityError` + `db.refresh(user)` backstop (matching `do_checkin`'s pattern) still covers the narrow case of two truly concurrent requests both passing that check at once.
- **Favorites and ratings**: `POST`/`DELETE /games/{slug}/favorite`, `POST /games/{slug}/rating` (1-5, upserts — a re-rating replaces, not stacks). `GET /games` now also returns `is_favorite`, `recently_played` (any finished session in the last 14 days), and `average_rating` per game, plus `category` and `sort_by=trending` query params.
- **Trending**: `games.trending_score` is recomputed by `app/workers/update_trending.py` as the count of finished sessions in the last 3 days per game — deliberately windowed so a game sinks back down once it's no longer actually being played, rather than a point-in-time counter that only ever goes up.
- **Friends leaderboard**: `GET /leaderboards/friends` — unlike the XP/game leaderboards it reads straight from Postgres (`app/services/friends.py:friend_ids`), not Redis, because the plan calls for it to be "referral and challenge connections": the referrer/referred graph plus anyone who's challenged-or-been-challenged-and-beaten the current user. Small per-user graph, no need for a sorted set.
- **Score cards**: `POST /share/score-card` (`{game_slug, variant?, score}`) renders a 1200x630 PNG with Pillow (game title, score, player name) and caches it on disk keyed by a hash of its inputs — a repeat share of the same result is a free lookup, not a re-render. Returns `PUBLIC_BASE_URL/media/score_cards/<hash>.png`, served by a `StaticFiles` mount. The card design is intentionally plain (default bitmap font, flat colors, no custom branding assets) — a real visual pass is a frontend/design task, not a backend one.

## Seasons, tournaments, sponsors, analytics (B5, plan section 13/16/21)

- **Seasons**: `GET`/`POST /admin/seasons` (only one can be `active` at a time — creating a second while one is active is `409`), `POST /admin/seasons/{id}/finalize`. Every XP-granting ledger row across the whole app (`sessions.py`, `checkin.py`, `achievements.py`, `referrals.py`, `challenges.py`, `tasks.py`, and the two admin XP-write endpoints — 10 creation sites in total) now stamps `xp_events.season_id` with whatever season is currently active, per the plan's literal wording. `GET /leaderboards/season` reads a live `sum(amount) group by user` straight from that ledger (not a Redis sorted set — the plan itself calls the Redis version "rebuildable" from this same table, and a season board doesn't need per-grant real-time ranking the way the global/per-game boards do). Finalizing a season freezes standings into `season_results`, pays rank-based XP (`settings.season_rank_xp`, default `{1: 500, 2: 300, 3: 150}`) with a `season_end` notification to each paid rank, and starts the next season back-to-back so there's never a gap with no active season. `app/workers/end_season.py` runs this automatically for any season whose `ends_at` has passed; `POST /admin/seasons/{id}/finalize` is the same logic for ops/testing.
- **Tournaments**: `GET /tournaments` (upcoming/active only), `GET /tournaments/{id}`, `GET /tournaments/{id}/entries`, `POST /tournaments/{id}/join`, admin `POST /admin/tournaments` and `POST /admin/tournaments/{id}/close`. Joining is required for a run to count — matches the plan's explicit `POST /tournaments/{id}/join` entry point rather than auto-enrolling every player of that game. Two scoring rules: `best_score` (keeps the max run) and `sum_top_n` (sums the best `top_n` runs — every run's score is kept in `tournament_entries.run_scores` so a later high score can correctly displace an earlier one from the top N, which a running sum alone can't express). Closing ranks entries by score, pays rank-based XP (`settings.tournament_rank_xp`, default `{1: 300, 2: 200, 3: 100}`), and notifies every entrant with their final rank. `app/workers/close_tournaments.py` runs this automatically past `ends_at`.
- **Daily/weekly challenge rotation**: reuses the existing task engine rather than a parallel system — mark an ordinary `play_game` Task (`period: 'daily'` or `'weekly'`) with `payload.rotates = true`, and `app/workers/rotate_daily_challenges.py` picks it a fresh random active game + a target score (10% of that game's `max_score`, a placeholder fraction not tuned against real play data) once per period, stamping `payload.rotated_on` so it only rotates once per day/week. Per-user completion tracking needed zero new code — a new day/week already means a fresh `period_key` on `UserTask`.
- **Sponsors**: `GET`/`POST /admin/sponsors`, and `tasks.sponsor_id` is now a real FK (was a plain nullable int since B3, with no table to point at). `GET /admin/sponsors/{id}/report` sums completions and XP **from the ledger** (`sum(xp_events.amount) where ref_type='task' and ref_id=<task id>`), not `completions * xp_reward` — stays correct even if a task's reward changed after some completions were already paid at the old rate.
- **Analytics**: one endpoint, `GET /admin/analytics/overview` — DAU (distinct users with a session today), day-1 retention (of users who signed up yesterday, the fraction with any session today — `null` if that cohort is empty), runs per game over the last 7 days, task completion rate, referral conversion rate. Plain SQL aggregates, no dashboard UI — same "admin API only" precedent as the rest of this backend.
- **Partitioning — planned, not built.** The plan's own wording for this item is "monthly partitioning **plan**," and its section 6 notes already say to start unpartitioned for the MVP and plan the migration "before the tables get large" — not now, with `scores`/`xp_events` still near-empty in every environment this was built against. The design, so it's ready when it's actually needed: convert both tables to PostgreSQL native range partitioning on `created_at`, one partition per month, created slightly ahead of time by a monthly job; move `xp_events.idempotency_key`'s uniqueness off the partitioned table itself (a unique constraint on a partitioned table must include the partition key, which `idempotency_key` strings don't carry) into a small separate table `(idempotency_key TEXT PRIMARY KEY, xp_event_id BIGINT)` that every ledger write checks/inserts into first; add an archive job that detaches and exports partitions older than some retention window instead of ever running a slow `DELETE` on a huge table. This is a schema migration with real downtime/locking risk on a live table, so it should be done once there's an actual growth curve to size it against, not speculatively now.

## Launch readiness (B6, plan sections 18/19/21)

### Security review

A manual pass against plan section 18's own checklist, not a tool scan. Real findings, all fixed:

- **Unhandled exceptions were silently swallowed.** `app/core/errors.py`'s catch-all handler returned a generic 500 to the client but never logged anything — a real bug (or an attacker probing for one) would leave zero trace anywhere. Now calls `logger.exception(...)` before responding.
- **Two routes were missing rate limits the plan explicitly names.** `POST /sessions/{id}/finish` had only a per-IP limit, no per-user one; `POST /tasks/{id}/verify` (and `/start`) had neither. Plan section 17 is explicit: "session starts, finish calls, task verifies" all need per-user *and* per-IP. Fixed; also added a blanket per-admin rate limit at `include_router()` time for the admin-only routers (`admin`, `seasons`, `tournaments.admin_router`, `analytics` — `tasks.router` mixes player and admin routes in one router object and is excluded from this blanket limit, though its admin endpoints are still gated by `require_admin`).
- **A null byte in a search query 500'd instead of returning "no results."** `GET /admin/users?search=` passed the raw string into `ILIKE`; Postgres' UTF-8 encoding can't contain `\x00`, so asyncpg raised and the generic handler turned it into a 500. Not a SQL injection (the ORM still parameterized it correctly) but still a real crash-on-malformed-input bug, exactly what plan section 18's "oversized inputs"/"injection attempts" test category is meant to catch. Fixed by stripping NUL bytes before the query.
- **The JWT secret had an insecure, well-known default and nothing stopped it shipping that way.** Added a startup check (`app/main.py:_check_secrets`): refuses to start in `ENVIRONMENT=production` with the default secret still active, just warns everywhere else so local dev isn't blocked.
- Added `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, and `Strict-Transport-Security` response headers. Deliberately **not** `X-Frame-Options` or a frame-ancestors CSP — this is a Telegram Mini App, which Telegram embeds in an iframe by design; a framing restriction here would break the one legitimate way this API's frontend is ever loaded.
- Confirmed already correct, no change needed: `hmac.compare_digest` for `initData` signature checks, JWT algorithm pinned to `HS256` (no algorithm-confusion risk), cross-user session/heartbeat access correctly 404s (not 403, so it doesn't leak whether the session exists), CORS already scoped to a single origin rather than `*`.
- 24 new tests (`tests/test_security_integration.py`, `tests/test_startup_secrets.py`) covering missing/malformed/garbage tokens, a banned user's token, cross-user session access, wrong session tokens, oversized string fields and request bodies, SQL-injection-shaped strings in search and in a path parameter, and the new response headers.

### Load testing

`scripts/locustfile.py` (Locust) exercises the traffic mix plan section 20 estimates for 100k users/10k DAU — mostly catalog/leaderboard/profile reads, a minority of score submissions. Run it with `scripts/seed_load_test_users.py` first (pre-mints JWTs directly rather than going through `POST /auth/telegram` per simulated user, which would immediately trip that route's own 30/hour-per-IP limit — a load generator is, by definition, one IP).

**Real bottleneck found and fixed**: at 150 concurrent simulated users against a single `uvicorn` process, median response time degraded from ~70ms (at 50 users) to ~2.4 **seconds**, with request throughput capped around 24-66 req/s — well under the plan's own 50-100 req/s peak target. Root cause, in order of what was tried:
1. First suspected the DB connection pool — SQLAlchemy's default (`pool_size=5` + `max_overflow=10` = 15 total connections) meant request #16 onward just queued for a free connection rather than erroring, showing up as rising latency with zero failures. Widened it to a configurable `DB_POOL_SIZE`/`DB_MAX_OVERFLOW` (default 20+20, comfortably under Postgres' own `max_connections=100`) — see `app/core/db.py`.
2. That alone made things **worse** (median rose to ~2.4s): a wider pool let more requests start executing concurrently in the *same single Python process*, and CPU-bound work (Pydantic validation/serialization, the rate limiter's Redis round-trips, business logic) all competes for one process's one event loop regardless of how many DB connections are available.
3. Running `uvicorn --workers 4` (still with the wider pool) fixed it: ~108 req/s sustained, median 170ms, p99 1.5s at 150 concurrent users — comfortably inside the plan's target. This isn't a "later, at 10x the users" scaling concern the way plan section 19's growth path frames it — a *single* process cannot hit the plan's own stated peak estimate at all, multi-process is needed from day one of real production traffic, not deferred to "when it grows."

### Backups

`scripts/backup.sh` (`pg_dump --format=custom`, retention cleanup) and `scripts/restore.sh` (`createdb` + `pg_restore`). **Actually tested**, not just written: backed up the real dev database, restored it into a fresh scratch database, verified row counts *and* content matched exactly across `users`/`games`/`scores`/`xp_events`, confirmed constraints (unique `referral_code`, etc.) survived, then dropped the scratch database. "Off-server storage" (shipping the dump to S3/GCS/etc.) is explicitly left as a one-line addition for whichever provider the real deployment ends up using — none exists in this environment to test against honestly.

### Data deletion

`DELETE /me` (plan section 18: "a simple data-deletion path for users who ask"). Anonymizes `username`/`first_name`/`last_name`/`photo_url` and sets `deleted_at`; the row itself and everything it's referenced by (`scores`, `xp_events`, ledger history) stay — same "never delete, only mark" principle already used for admin XP reversals, applied to personal data. `get_current_user` rejects any token for a deleted account with `401` (closes the window where a JWT issued just before deletion would otherwise still work for up to its remaining TTL). Re-opening the Mini App afterward (fresh, real `initData`) is treated as renewed consent and clears `deleted_at`, restoring a fresh profile under the same Telegram id.

### CI

`../.github/workflows/backend-ci.yml`: lint (`ruff`), run Alembic migrations, run the full test suite — all against a real Postgres service container, not SQLite or mocks. Fixed a real portability bug surfaced while writing this: `tests/conftest.py` hardcoded its test database URL as a literal constant instead of reading `TEST_DATABASE_URL` from the environment, which would have made this workflow fail trying to connect as this environment's local peer-auth role on a CI runner that has no such role. Now reads from env with the same literal as its fallback default, so local behavior is unchanged.

**Not verified**: whether `ruff check .` actually passes clean — `pip install ruff` could not complete in this sandbox (repeated attempts stalled indefinitely mid-download on a plain, dependency-free 10MB wheel, while `pypi.org`'s API itself responded instantly and other, similarly-sized packages like Pillow installed in seconds earlier in this project — looks like a transient/throttled network path specific to this sandbox rather than anything about the package or the code). The workflow step itself should run fine in GitHub Actions' own environment; just flag this if CI's first real run surprises you with lint findings nobody caught locally.

### Privacy, terms, launch

`../PRIVACY.md` and `../TERMS.md` — drafts describing what the app actually does (data collected, retention, the deletion path above, fair-play/anti-cheat policy), explicitly marked as **not legal advice** and needing a real lawyer's review before publishing; written so a reviewer has an accurate starting point rather than a generic template that might contradict the real implementation.

**Not attempted** (genuinely needs infrastructure this environment doesn't have, not a code gap): a real staging/production deployment, live monitoring/alerting wired to an actual Sentry/Grafana account, shipping backups to real off-server storage, and the soft-launch/public-launch steps themselves (plan section 21 B6 points 5-6) — all need real users, a real bot, and a real host.

## Running tests

```bash
createdb alphago_test   # once
pytest
```

`tests/conftest.py` explains why this uses a real local Postgres database instead of testcontainers (plan section 18's recommendation) — the docker daemon in the environment this was built in has no outbound network access, so `docker pull` for the Postgres/Redis test images never completes. A CI environment with working Docker networking should be able to switch to testcontainers with changes isolated to that one file.

## About Docker

`Dockerfile` and `docker-compose.yml` are written to match the plan's architecture (section 3/19) but have **not been built or run** in this environment — same network restriction as above applies to `docker pull python:3.12-slim` and the Postgres/Redis images. Try `docker compose up --build` wherever this actually deploys; if it doesn't work immediately, check the base images pull successfully first.

## Web frontend (`web-frontend/alpha/`)

A real Mini App shell now exists there (was an empty Vite scaffold before) — login, catalog, full game-session lifecycle via the `games/` postMessage bridge, leaderboards, tasks, and profile, all wired to this API. See `web-frontend/alpha/README.md` for its architecture.

Building it against this API for real surfaced one backend bug: `app/services/game_import.py` stored `thumbnail_url` as the raw manifest filename (e.g. `"thumb.svg"`) instead of resolving it to an absolute URL the way `entry_url` already did — every game card's thumbnail was a broken `<img>` pointing at the frontend's own origin. Fixed with a `_thumbnail_url()` helper mirroring `_entry_url()`; re-ran `python -m app.workers.import_manifests` against the real dev database to fix the already-stored rows. Full suite re-verified (339 passed) since no test covered `game_import.py` directly.

## What's NOT built yet

Deliberately deferred to their named phases rather than built speculatively now:

- **Group leaderboards (`GET /leaderboards/groups/{chat_id}`)** — needs `my_chat_member` tracking of which groups the bot is in, which needs the bot (next bullet).
- **The bot itself** (`app/bot/` is an empty package) — no aiogram handlers, no webhook wiring. `BOT_TOKEN` in `.env.example` is a placeholder; the Telegram client code (`app/core/telegram_client.py`) is written to the documented API shape but unverified against the real API. This also blocks: `/top` in groups, broadcast-style notifications (`new_task`, `tournament_start` — no fan-out producer exists, see "Notifications" above), Telegram's own share-sheet for challenge/referral links (the API still returns a valid deep link either way), and `my_chat_member` (`bot_blocked`, group membership).
- **A real admin UI, the `getChatMember` verification queue+throttle, a Redis leaderboard rebuild job, the streak-reminder job, per-user time zones** — all explicitly named as such in the plan, all genuinely deferred (not forgotten).
- **Score-card visual design** — the current render is a plain placeholder (default font, flat background); a real design pass belongs with the frontend work, not this backend pass.
- **Amharic/Afaan Oromo translation review** — the notification template strings exist and render correctly (see above) but are a best-effort non-native pass, not reviewed by a native speaker. Game/achievement/task *content* (titles/descriptions) also stay English-only — the JSONB-per-locale shape already supports more languages, but filling in real am/om game content is a content-authoring task, not a backend code task.
- **Partitioning** — designed, not implemented; see the B5 section above for why and for the actual plan to follow once it's needed.
- **Badges, as a concept distinct from achievements** — the plan's section 13 says seasons/tournaments pay "XP and badges"; this pass pays XP only (the existing `achievements` system already covers "unlock something permanent," and no separate badge system was built on top of it).
- **A real staging/production deployment, live monitoring/alerting (Sentry/Grafana wired to a real account), shipping backups to real off-server storage, soft/public launch** — all B6 items that genuinely need infrastructure (a host, a real bot, real users) this environment doesn't have; see the B6 section above for exactly what *was* verified locally instead (a tested backup/restore, a load test that found and fixed a real bottleneck, a security review, the data-deletion path, and a CI workflow).
- **`ruff check .` passing clean, verified locally** — `pip install ruff` could not complete in this sandbox (see the B6/CI section above); the lint step is wired into CI regardless and should run fine there.

## Verified end-to-end in this session

Real local Postgres, no mocking of the database layer. B0-B2 coverage (auth, catalog, sessions/finish, XP/levels, leaderboards, check-in/streaks, achievements, profile, basic admin) is unchanged from before — see git history / earlier summaries for that list. **B3 (task engine, admin moderation, notifications, anti-cheat, per-IP rate limiting)** is also unchanged. **B4 (referrals, challenges, favorites/ratings/categories/trending, score cards, friends leaderboard)** is also unchanged — see the previous revision of this file for both lists.

**New in B5, all verified via real HTTP integration tests against the real database:**

- Seasons: only one season can be active at a time (`409` on a second); a game run's XP ledger row is correctly stamped with the active season's id; `GET /leaderboards/season` ranks by summed season XP and 404s when no season is active; finalizing freezes `season_results` with the right rank, pays the default rank-1 XP bonus, and immediately starts "Season 2" back-to-back.
- Tournaments: a run before `join` doesn't count, the same run after `join` does; `best_score` keeps the max of several runs; `sum_top_n` correctly sums only the best `N` (verified with `top_n=2` across three runs of different sizes, not just two); closing assigns ranks in score order, pays the default rank-1 reward, and can't be run twice (`409` on a second close).
- Sponsors: creating a sponsor and associating it with a task round-trips through the real FK; the sponsor report correctly sums completions and XP across two different users' completions of the same task; an unknown sponsor id 404s.
- Multi-language notifications: all three languages render correctly with their placeholders substituted; an unsupported language code falls back to English; an unknown notification type or a missing placeholder both degrade gracefully instead of crashing.
- Analytics: the overview endpoint reflects a real session (DAU and runs-per-game both pick it up) and degrades to `null` rather than crashing when a cohort (yesterday's signups, task starts, referrals) is empty; non-admins get `403`.
- Daily/weekly challenge rotation: **verified by manual run against the real dev database** (not pytest — same precedent as every other due-job worker in this codebase, e.g. `update_trending.py`; none of them have a database to run against inside the pytest fixtures' isolated test engine). Created a real `rotates: true` task, ran the worker, confirmed its payload actually changed to a real active game + a real computed target score, confirmed a second same-day run is a no-op, then deleted the test task.

**New in B6, all verified for real (not just written):**

- Security: see the B6 section above — 24 new tests covering auth edge cases, cross-user access, oversized/malformed/injection-shaped input, and the new response headers; one real crash bug (null byte in admin search) and one real silent-logging bug found and fixed along the way.
- Backups: an actual `pg_dump` of the real dev database, restored into a scratch database, with row counts *and* content spot-checked to match, then the scratch database dropped.
- Load test: found a real bottleneck (a single `uvicorn` process can't hit the plan's own stated peak target) and verified the fix (wider DB pool + multiple worker processes) actually resolves it, with before/after numbers.
- Data deletion: anonymization, old-token rejection, and re-auth-restores-access all verified via real HTTP calls against the real database.
- CI: the workflow file itself wasn't run (no GitHub Actions access from here), but the bug it would have hit (`conftest.py`'s hardcoded test DB URL) was found and fixed by reading the file closely, not by running the workflow.

339 tests, all passing.

**Not verified** (would need a real Telegram bot token, a live deployment, a browser/device, or GitHub Actions access — none available in this environment): this API opening *inside real Telegram* specifically (the web-frontend shell above was smoke-tested end-to-end against this API in a plain Chrome tab via a dev-sim login, not inside an actual Telegram client), the bot's webhook, `join_channel` and the notification worker against the real Telegram Bot API, the CI workflow actually running, and `ruff check .` passing clean.
