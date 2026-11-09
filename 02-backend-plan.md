# AlphaGo, Part 2: Backend Plan

Companion files: `01-game-adaptation-plan.md` (games and bridge) and `alphago-project-plan.md` (original overview).
Where this file differs from the overview, **this file wins**.

Target scale: up to **100k registered users and about 10k daily active users**.

---

## 1. Scope

The backend covers:

- Telegram authentication (`initData` validation) and user accounts
- Game catalog (imported from game manifests) and game sessions
- Score submission, validation, and XP rewards
- Levels, streaks and daily check-in, achievements
- Tasks (with verification) and notifications
- Referrals, challenges, friends/group leaderboards, tournaments, seasons
- Leaderboards (Redis) with Postgres as the source of truth
- Bot (commands, deep links, notification sending)
- Admin panel API (games, tasks, users, audit log)
- Anti-cheat, rate limiting, observability, deployment

Out of scope: the games themselves and the iframe bridge (Part 1), and the Mini App frontend UI (only its API needs are specified here).

## 2. Technology Choices

Pick one stack and stay consistent. Recommended default is Python because the bot ecosystem (aiogram) and rapid API development fit well, and everything below is easy to port to Go or TypeScript.

| Layer | Recommended default | Alternatives |
|---|---|---|
| Language | Python 3.12 | Go, TypeScript |
| API framework | FastAPI (async) | Go (Fiber/Gin), NestJS |
| Bot | aiogram 3 (webhook mode) | grammY (TypeScript) |
| ORM and migrations | SQLAlchemy 2 + Alembic | sqlc + goose (Go), Prisma |
| Database | PostgreSQL 16 | none |
| Cache, leaderboards, queues | Redis 7 | none |
| Background jobs | ARQ (Redis, async) | Celery, Asynq (Go), BullMQ |
| Validation | Pydantic v2 | zod (TS) |
| Auth tokens | JWT (short-lived) via PyJWT | none |
| Reverse proxy and TLS | Caddy or Nginx | Cloudflare in front |
| Containers | Docker + docker-compose | none |
| Monitoring | Sentry + Prometheus metrics endpoint (Grafana optional) | none |
| Testing | pytest, httpx, testcontainers, k6 for load | none |
| CI | GitHub Actions | none |

## 3. Architecture

One **modular monolith** deployed as three processes from the same codebase. This is simpler to build and debug than microservices and is more than enough for 10k DAU.

```
Telegram  --webhook-->  bot  (aiogram handlers, same codebase)
Mini App  --HTTPS---->  api  (FastAPI)  --> PostgreSQL
                          |                    ^
                          +--> Redis <---------+
                          |      ^
                          v      |
                        worker (ARQ jobs: notifications, verification, seasons, imports)
```

Processes
- **api:** REST API plus the Telegram webhook endpoint (can also be split off as its own process later).
- **worker:** background jobs and scheduled jobs.
- **bot handlers:** run inside the api process or as a separate process; they share services with the API.

Principles
1. The client is never trusted. Every request carries a token derived from validated Telegram `initData`.
2. Games report only a score; the **session token never touches the game** (the wrapper holds it).
3. Every XP change is a row in an **append-only ledger** (`xp_events`) with an idempotency key.
4. Tunable values (XP rates, caps, rewards) live in the database or settings table, not in code.
5. Postgres is the source of truth; Redis can be rebuilt from it at any time.
6. Long or rate-limited work (notifications, `getChatMember` calls) goes through queues.

### Repository layout

```
backend/
  app/
    main.py                  # FastAPI app factory, middleware
    core/                    # config, security (initData, JWT), db, redis, logging, errors
    models/                  # SQLAlchemy models
    schemas/                 # Pydantic request/response models
    api/v1/                  # routers: auth, me, games, sessions, leaderboards, checkin,
                             #   tasks, achievements, referrals, challenges, tournaments, admin
    services/                # business logic: xp, levels, scores, checkin, tasks,
                             #   achievements, referrals, leaderboards, notifications, seasons
    workers/                 # ARQ job definitions and cron schedule
    bot/                     # aiogram routers, keyboards, message templates (i18n)
  migrations/                # Alembic
  tests/                     # unit, integration, load (k6 scripts)
  docker-compose.yml
  Dockerfile
  .env.example
```

Keep **routers thin** (parse, authorize, call a service) and put rules in `services/`, so the same logic serves the API, the bot, and the worker.

## 4. Configuration (environment variables)

| Variable | Purpose |
|---|---|
| `BOT_TOKEN` | Telegram bot token (secret) |
| `BOT_USERNAME`, `MINI_APP_SHORT_NAME` | For building deep links |
| `WEBHOOK_URL`, `WEBHOOK_SECRET` | Webhook endpoint and its secret header token |
| `DATABASE_URL`, `REDIS_URL` | Connections |
| `JWT_SECRET`, `JWT_TTL_SECONDS` | API tokens (for example 3600) |
| `APP_ORIGIN`, `GAMES_ORIGIN` | CORS and iframe origin checks |
| `INITDATA_MAX_AGE_SECONDS` | Reject stale `initData` (for example 86400) |
| `ADMIN_TELEGRAM_IDS` | Bootstrap admin allowlist |
| `SENTRY_DSN` | Error reporting |
| `NOTIFY_RATE_PER_SECOND` | Notification throttle (for example 25) |

Secrets live in the host's secret store or `.env` outside git; never in the repository.

## 5. Authentication

### 5.1 Validating Telegram `initData`

The Mini App sends the raw `initData` string with its first request. The server validates it and exchanges it for a short-lived JWT.

Algorithm (from Telegram's documented scheme; double-check against the current docs when implementing):
1. Parse the query string into key/value pairs.
2. Remove the `hash` field. Sort the remaining pairs alphabetically and join as `key=value` lines separated by `\n` to get the data-check string.
3. `secret_key = HMAC_SHA256(key="WebAppData", message=BOT_TOKEN)`.
4. `expected = hex(HMAC_SHA256(key=secret_key, message=data_check_string))`.
5. Compare with `hash` using a constant-time comparison.
6. Check `auth_date` is recent (reject if older than `INITDATA_MAX_AGE_SECONDS`).
7. Parse the `user` JSON field for `id`, `first_name`, `username`, `language_code`, `photo_url`.

```python
import hmac, hashlib, json, time
from urllib.parse import parse_qsl

def validate_init_data(init_data: str, bot_token: str, max_age: int) -> dict:
    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        raise ValueError("missing hash")
    data_check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received_hash):
        raise ValueError("bad signature")
    if time.time() - int(pairs.get("auth_date", 0)) > max_age:
        raise ValueError("initData too old")
    return {"user": json.loads(pairs["user"]), "start_param": pairs.get("start_param")}
```

### 5.2 Token exchange

- `POST /auth/telegram` with `{ init_data }` returns `{ access_token, expires_in, user }`.
- On first sight of a `telegram_id`, create the user (generate a random `referral_code`) and, if `start_param` carries a referral code, record the referral (section 12).
- Subsequent requests use `Authorization: Bearer <JWT>`. When the JWT expires, the frontend silently calls `/auth/telegram` again with fresh `initData`.
- Banned users get `403` on everything except a minimal "you are banned" response.

## 6. Data Model (MVP schema)

SQL below is the intended shape for Milestones 1 to 3. Types are PostgreSQL; adjust names as you like.

```sql
CREATE TABLE users (
  id BIGSERIAL PRIMARY KEY,
  telegram_id BIGINT NOT NULL UNIQUE,
  username TEXT, first_name TEXT, last_name TEXT, photo_url TEXT,
  language TEXT NOT NULL DEFAULT 'en',
  total_xp BIGINT NOT NULL DEFAULT 0,
  level INT NOT NULL DEFAULT 1,
  streak_count INT NOT NULL DEFAULT 0,
  streak_freezes INT NOT NULL DEFAULT 0,
  last_checkin_date DATE,
  referral_code TEXT NOT NULL UNIQUE,
  referred_by BIGINT REFERENCES users(id),
  notifications_enabled BOOLEAN NOT NULL DEFAULT TRUE,
  bot_blocked BOOLEAN NOT NULL DEFAULT FALSE,
  is_banned BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_seen_at TIMESTAMPTZ
);

CREATE TABLE games (
  id SERIAL PRIMARY KEY,
  slug TEXT NOT NULL UNIQUE,
  version TEXT NOT NULL,
  title JSONB NOT NULL, description JSONB,
  category TEXT NOT NULL,
  thumbnail_url TEXT, entry_url TEXT NOT NULL,
  variants TEXT[] NOT NULL DEFAULT '{}',
  max_score BIGINT NOT NULL,
  min_play_seconds INT NOT NULL,
  max_score_per_second NUMERIC NOT NULL,
  xp_rate NUMERIC NOT NULL,
  max_xp_per_run INT NOT NULL,
  license_code TEXT, license_assets TEXT, author TEXT, source_url TEXT,
  size_kb INT,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','active','disabled')),
  trending_score NUMERIC NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE game_sessions (
  id UUID PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES users(id),
  game_id INT NOT NULL REFERENCES games(id),
  variant TEXT,
  token_hash BYTEA NOT NULL,
  seed TEXT,
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','finished','expired','rejected')),
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ,
  last_heartbeat_at TIMESTAMPTZ,
  active_seconds INT NOT NULL DEFAULT 0
);
CREATE INDEX ON game_sessions (user_id, started_at DESC);

CREATE TABLE scores (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES users(id),
  game_id INT NOT NULL REFERENCES games(id),
  session_id UUID NOT NULL UNIQUE REFERENCES game_sessions(id),
  variant TEXT,
  value BIGINT NOT NULL,
  xp_awarded INT NOT NULL DEFAULT 0,
  flagged BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON scores (game_id, variant, value DESC);
CREATE INDEX ON scores (user_id, game_id, created_at DESC);

CREATE TABLE xp_events (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES users(id),
  source TEXT NOT NULL,                 -- game, checkin, task, referral, achievement, tournament, admin
  amount INT NOT NULL,                  -- can be negative for reversals
  ref_type TEXT, ref_id TEXT,
  season_id INT,
  idempotency_key TEXT NOT NULL UNIQUE, -- e.g. 'score:<session_id>', 'checkin:<user>:<date>'
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON xp_events (user_id, created_at DESC);
CREATE INDEX ON xp_events (season_id, user_id);

CREATE TABLE tasks (
  id SERIAL PRIMARY KEY,
  type TEXT NOT NULL,                   -- join_channel, play_game, invite_friends, open_link, daily_open, custom
  title JSONB NOT NULL, description JSONB,
  payload JSONB NOT NULL DEFAULT '{}',
  xp_reward INT NOT NULL,
  period TEXT NOT NULL DEFAULT 'once' CHECK (period IN ('once','daily','weekly')),
  verify_method TEXT NOT NULL,          -- auto, timed_claim, manual
  sponsor_id INT,
  starts_at TIMESTAMPTZ, ends_at TIMESTAMPTZ,
  max_total_completions INT,
  active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE user_tasks (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES users(id),
  task_id INT NOT NULL REFERENCES tasks(id),
  period_key TEXT NOT NULL,             -- 'once' | '2026-11-03' | '2026-W45'
  status TEXT NOT NULL DEFAULT 'started' CHECK (status IN ('started','pending_review','completed','rejected')),
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at TIMESTAMPTZ,
  UNIQUE (user_id, task_id, period_key)
);

CREATE TABLE achievements (
  id SERIAL PRIMARY KEY,
  key TEXT NOT NULL UNIQUE,
  title JSONB NOT NULL, description JSONB, icon TEXT,
  condition JSONB NOT NULL,             -- e.g. {"type":"streak","value":7}
  xp_reward INT NOT NULL DEFAULT 0
);
CREATE TABLE user_achievements (
  user_id BIGINT NOT NULL REFERENCES users(id),
  achievement_id INT NOT NULL REFERENCES achievements(id),
  unlocked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, achievement_id)
);

CREATE TABLE referrals (
  id BIGSERIAL PRIMARY KEY,
  referrer_id BIGINT NOT NULL REFERENCES users(id),
  referred_id BIGINT NOT NULL UNIQUE REFERENCES users(id),
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','rewarded','rejected')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  rewarded_at TIMESTAMPTZ
);

CREATE TABLE notification_outbox (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES users(id),
  type TEXT NOT NULL,
  payload JSONB NOT NULL DEFAULT '{}',
  status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','sent','failed','skipped')),
  attempts INT NOT NULL DEFAULT 0,
  scheduled_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  sent_at TIMESTAMPTZ
);
CREATE INDEX ON notification_outbox (status, scheduled_at);

CREATE TABLE settings (key TEXT PRIMARY KEY, value JSONB NOT NULL);   -- tunables: caps, rewards, curves
CREATE TABLE admin_users (user_id BIGINT PRIMARY KEY REFERENCES users(id), role TEXT NOT NULL DEFAULT 'admin');
CREATE TABLE audit_log (
  id BIGSERIAL PRIMARY KEY, admin_id BIGINT NOT NULL, action TEXT NOT NULL,
  target_type TEXT, target_id TEXT, details JSONB, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

**Later-phase tables** (add when you reach those phases): `seasons`, `season_results`, `challenges`, `challenge_entries`, `tournaments`, `tournament_entries`, `favorites`, `game_ratings`, `groups`, `sponsors`.

Notes
- **Partitioning:** `scores` and `xp_events` can grow to tens of millions of rows a year. Start unpartitioned for the MVP. When you partition by month, unique constraints must include the partition key, so keep `idempotency_key` uniqueness enforced through a small separate table, or include `created_at` in the constraint, and plan that migration before the tables get large.
- `users.total_xp` and `level` are cached values; `xp_events` is the source of truth and can recompute them.
- Keep `variant` on scores so leaderboards per board size or difficulty stay separate.

## 7. Game Catalog and Import

- A **manifest import job** (admin-triggered or CI-triggered) reads each game's `game.json` (Part 1, section 5.3) and upserts into `games`. New games arrive as `pending`; an admin reviews and sets `active`.
- `entry_url` = `https://games.yourdomain.com/<slug>/<version>/index.html`. Changing a game's version updates `entry_url` and `version`; old versions stay reachable.
- Validate manifest fields (ranges, required keys, license present) before accepting.
- `GET /games` returns only `active` games, with the user's best score per game and flags (favorite, recently played) added.

## 8. Game Sessions and Score Flow (the core)

### 8.1 Sequence

```
Mini App                          API                               DB / Redis
   |-- POST /games/{slug}/sessions ->|                                   |
   |   {variant}                     |-- create session, random token -->|
   |<- {session_id, token, seed} ----|    (store only hash of token)     |
   |  (iframe gets "start")                                              |
   |  ... player plays ...                                               |
   |  (game sends "gameover")                                            |
   |-- POST /sessions/{id}/finish -->|                                   |
   |   {token, score, variant, meta} |-- validate, award XP, update ---->|
   |<- {result: xp, level, ranks} ---|                                   |
```

### 8.2 Creating a session

- Requires auth. Rate limit: for example 60 starts per user per hour.
- Create `game_sessions` row, `status='active'`, a random 32-byte token (returned once, stored only as a hash), an optional `seed` (daily puzzles use a deterministic seed per date, such as a hash of date + game + variant).
- Any previous `active` session for the same user and game is marked `expired` (one active run per game).

### 8.3 Finishing a session (validation rules)

All inside one database transaction, with `SELECT ... FOR UPDATE` on the session row:

1. Session exists, belongs to this user, `status = 'active'`.
2. Token matches (constant-time compare of hash).
3. Session is not too old (for example 2 hours).
4. `duration = now - started_at` (server-measured). If `duration < min_play_seconds`, reject (`status='rejected'`, no XP).
5. `score` is an integer, `0 <= score <= max_score`.
6. `score / max(duration, 1) <= max_score_per_second`. If exceeded, mark `flagged=true`, store the run, award **no XP**, keep it out of leaderboards, and queue it for admin review.
7. `variant` is allowed for this game.
8. Idempotency: if the session is already `finished`, return the stored result (a repeated request cannot double-reward).

### 8.4 XP award

```
base_xp   = min(floor(score * game.xp_rate), game.max_xp_per_run)
runs_today = number of XP-awarding runs by this user in this game today (UTC)
multiplier = 1.0 if runs_today < 5
           = 0.5 if runs_today < 10
           = 0.25 if runs_today < 20
           = 0 otherwise
xp = floor(base_xp * multiplier)
xp = min(xp, daily_game_xp_cap - game_xp_earned_today)    # for example cap 1000, never below 0
```

All thresholds and the daily cap come from the `settings` table.

Then, in the same transaction:
1. Insert `scores` row (`xp_awarded = xp`).
2. Insert `xp_events` row with `idempotency_key = 'score:<session_id>'`. A conflict means this run was already processed.
3. Update `users.total_xp` and recompute `level` (row-level lock on the user).
4. Mark the session `finished`.

After commit (best effort, not blocking the response):
- Update Redis leaderboards (section 10).
- Publish an internal event `score_submitted` for achievements, tasks, challenges, and tournaments (section 11).

Response to the client: `{ score, xp_awarded, total_xp, level, level_progress, personal_best, rank, new_achievements[] }`.

### 8.5 Heartbeats (optional)

`POST /sessions/{id}/heartbeat` every 15 to 30 seconds while the game is visible. The server accumulates `active_seconds` (capped by wall-clock time). It is used for anti-cheat comparison (claimed vs active time) and analytics, not as a reward source.

## 9. XP, Levels, and Rewards

### 9.1 Levels

- Level 1 starts at 0 XP. XP required to reach level `n` is `round(100 * (n - 1)^1.5)`.
- Inverse: `level = 1 + floor((total_xp / 100)^(2/3))`.
- Level-ups generate a `level_up` notification and may trigger achievements.

(This slightly adjusts the earlier overview formula so that level 1 begins at 0 XP.)

### 9.2 XP sources

| Source | Amount | Controls |
|---|---|---|
| Game runs | `score * xp_rate`, capped | per-run cap, diminishing returns, daily game cap |
| Daily check-in | 10 + 5 * min(streak - 1, 6); +50 bonus on every 7th consecutive day | once per UTC day |
| Tasks | `tasks.xp_reward` | period and total completion limits |
| Referrals | for example 50 to referrer, 25 to new user | activation rule, caps |
| Achievements | `achievements.xp_reward` | one-time |
| Tournaments and seasons | rank-based XP and badges | event rules |

Everything is configurable through `settings`. Every grant is an `xp_events` row with an idempotency key built from its source (`checkin:<user>:<date>`, `task:<user>:<task>:<period_key>`, `achievement:<user>:<id>`, `referral:<referral_id>:<role>`).

### 9.3 Reversals

Admin actions (ban, fraud rollback) write **negative** `xp_events` rows with `source='admin'` and an audit log entry. Totals are recomputed from the ledger; nothing is deleted.

## 10. Leaderboards (Redis)

Redis sorted sets, rebuilt from Postgres when needed.

| Key | Contents |
|---|---|
| `lb:game:{game_id}:{variant}:best` | Best score per user for that game and variant (use `ZADD ... GT`) |
| `lb:xp:global` | Total XP per user |
| `lb:season:{season_id}` | Season XP per user |
| `lb:group:{chat_id}:xp` | XP for members of a Telegram group (or computed on demand) |
| `lb:tournament:{id}` | Best score in the tournament window |

- Ranks: `ZREVRANK`; top N: `ZREVRANGE ... WITHSCORES`; neighbors around a user for the "my rank" view.
- **Ties:** earlier achievement of a score should rank higher. Encode a timestamp component in the fractional part of the sort value, keeping within double precision.
- Cache the top 100 per leaderboard for a few seconds.
- Banned and flagged users are removed from all sets.
- A rebuild job reconstructs every key from `scores` and `xp_events`. Run it after Redis loss or when changing the tie-break encoding.
- Display names and avatars are fetched in one batch from Postgres for the page of user ids returned.

## 11. Event Handling: Achievements, Tasks, Challenges

An internal event bus (simple in-process publish after commit; move to a Redis stream when needed):

| Event | Fired by | Consumers |
|---|---|---|
| `score_submitted` | session finish | achievements, play_game tasks, daily/weekly challenges, tournaments |
| `checked_in` | check-in | achievements, streak notifications |
| `task_completed` | tasks service | achievements |
| `referral_activated` | referrals service | achievements, referral tasks |
| `level_up` | XP service | achievements, notifications |

### Achievements

- `achievements.condition` JSON, evaluated per event type. Examples: `{"type":"total_runs","value":10}`, `{"type":"streak","value":7}`, `{"type":"score_at_least","game":"2048","value":5000}`, `{"type":"level","value":5}`.
- On unlock: insert `user_achievements` (primary key prevents duplicates), award XP with an idempotency key, queue a notification, include in the API response when it happens during a request.

### Daily check-in and streaks

- `POST /checkin`: uses the **UTC date** (decision for the MVP; per-user time zones can come later).
- If `last_checkin_date == today`: return the current state (already checked in).
- If `last_checkin_date == yesterday`: `streak_count += 1`.
- If it is older: if `streak_freezes > 0` and the gap is at most 2 days, consume a freeze and continue the streak, otherwise reset to 1.
- Award XP (section 9.2) with idempotency key `checkin:<user>:<date>`.
- Freezes are earned through achievements or referrals, not purchased.

## 12. Tasks, Verification, Referrals

### 12.1 Task engine

- `GET /tasks`: active tasks within their time window, with per-user status for the current `period_key`.
- `POST /tasks/{id}/start`: creates the `user_tasks` row (`started`), returns any link to open (channel link, URL).
- `POST /tasks/{id}/verify`: runs the handler for the task's `type` and `verify_method`.
- Completion is one transaction: set `completed`, insert `xp_events` with `task:<user>:<task>:<period_key>`. The `UNIQUE (user_id, task_id, period_key)` constraint and idempotency key make double-claims impossible.
- `period_key`: `once`, the UTC date for daily, or `YYYY-Www` for weekly.
- Global caps: `max_total_completions` per task and a daily task-XP cap per user (in `settings`).

### 12.2 Handlers

| type | Verification |
|---|---|
| `join_channel` | Bot calls `getChatMember` (the bot must be an admin of the channel). Statuses `member`, `administrator`, `creator` pass. Queue the check and cache a positive result |
| `play_game` | Look up `scores` since the task started (game, optional minimum score or run count) |
| `daily_open` / check-in | Completed by `POST /checkin` |
| `invite_friends` | Count activated referrals since task start |
| `open_link` / `share_story` | **Timed claim:** verify only that the time since `start` exceeds a minimum (for example 15 seconds); give small XP |
| `custom` | `manual`: status `pending_review`; admin approves or rejects |

Rate limits: `getChatMember` calls go through a queue and a throttle, because Telegram rate limits apply to them as well.

### 12.3 Task notifications

When an admin publishes a task, the worker enqueues `notification_outbox` rows for eligible users (see section 14). The message has an inline button that opens the Mini App on the task via `startapp` (for example `startapp=task_42`).

### 12.4 Referrals

- Link: `https://t.me/<bot>/<app>?startapp=r_<referral_code>`. Use the random `referral_code`, not the Telegram id. `startapp` allows only letters, digits, underscore, and hyphen, up to 64 characters.
- On first auth with `start_param = r_<code>`: create a `referrals` row (`pending`) if the code exists, it is not the user's own, and the new user has no referrer yet.
- **Activation:** the referral becomes `rewarded` when the referred user completes their first valid scored run (not just opens the app). Then grant XP to both sides with idempotency keys.
- Abuse limits: per-referrer daily cap, total cap, no self-referral, flag referrers whose referrals are never active, and optionally require the referred account to survive 24 hours.

### 12.5 Challenges (friend duels)

- `POST /challenges` after a run: `{ game, variant, score_to_beat }` creates a challenge with a short token and expiry (for example 7 days).
- Share by opening `https://t.me/share/url?url=<deep link>&text=<message>` (via `openTelegramLink`), where the deep link is `https://t.me/<bot>/<app>?startapp=c_<token>`. Telegram also offers prepared-message sharing for Mini Apps; check the current docs if you prefer that.
- A friend opening the link plays that game; if they beat the target the challenger gets a notification and a small XP reward.

## 13. Seasons and Tournaments (later phases)

**Seasons**
- `seasons(id, name, starts_at, ends_at, status)`; every `xp_events` row stores the active `season_id`.
- Season leaderboard = sum of season XP (Redis set per season, rebuildable).
- End-of-season job: freeze the top results into `season_results`, award badges/XP to ranks, start the next season. All-time XP and level are unaffected.

**Tournaments**
- A tournament defines the game, variant, time window, and rule (best single score or sum of top N runs).
- Entries update `tournament_entries` and `lb:tournament:{id}` on each valid run in the window.
- A closing job finalizes ranks, grants XP and badges, and sends notifications.
- Prizes are XP and badges only (no economy).

## 14. Bot and Notifications

### 14.1 Bot setup

- Webhook mode: `setWebhook` with a secret token; the API route verifies the `X-Telegram-Bot-Api-Secret-Token` header.
- BotFather: set the menu button to open the Mini App, register the Mini App short name, and enable inline mode only if you need it.

### 14.2 Commands and deep links

| Entry | Behavior |
|---|---|
| `/start` | Welcome, button to open the Mini App; handles `start` parameters (referral `r_<code>`, challenge `c_<token>`, task `task_<id>`) |
| `/play` | Opens the Mini App |
| `/top` | In private chat: user's rank. In groups: top members of that group; stores the group in `groups` |
| `/settings` | Language and notification toggle (inline keyboard) |
| `/help` | Short help |
| Mini App links (`startapp=...`) | Read `start_param` in the Mini App and route to the right screen |

Handle `my_chat_member` updates to mark `bot_blocked` when a user blocks the bot and to record when the bot is added to groups.

### 14.3 Notification worker

Types: `new_task`, `streak_reminder`, `challenge_beaten`, `level_up`, `season_end`, `tournament_start/end`, `friend_joined`.

Design
1. Producers insert `notification_outbox` rows (or enqueue a "fan-out" job for broadcasts).
2. The worker pulls `queued` rows due now, in batches, through a **token bucket** at `NOTIFY_RATE_PER_SECOND` (about 25 per second overall, under Telegram's roughly 30 per second bot limit; also stay at about 1 message per second per chat).
3. On success: `sent`. On `429`: wait for `retry_after` and retry. On `403 bot was blocked`: set `users.bot_blocked = true`, mark `skipped`. On other errors: retry with backoff, then `failed`.
4. Broadcast audiences are ordered by recent activity so engaged users get messages first. A 100k-user broadcast takes about an hour at 25 per second, so announce big events early and avoid time-critical promises.
5. Respect `notifications_enabled`, skip blocked users, apply daily limits (for example at most 2 non-critical notifications per user per day), and optionally quiet hours once you store time zones.
6. Messages are localized from templates by `users.language`.

Streak reminder job: runs hourly, selects users with an active streak who have not checked in today and whose reminder time has arrived.

## 15. REST API Specification (summary)

All routes are under `/api/v1`, JSON, authenticated with `Authorization: Bearer <JWT>` unless noted. Errors use a consistent shape: `{ "error": { "code": "...", "message": "..." } }`.

| Area | Method and path | Purpose |
|---|---|---|
| Auth | `POST /auth/telegram` (no auth) | `initData` to JWT |
| Profile | `GET /me` | Profile, XP, level, streak, badges summary |
| | `PATCH /me` | Language, notification settings |
| | `GET /me/xp-history?cursor=` | Paged ledger |
| Games | `GET /games` | Active catalog with user's bests |
| | `GET /games/{slug}` | Detail, variants, credits |
| | `POST /games/{slug}/sessions` | Start a run |
| | `POST /sessions/{id}/heartbeat` | Optional liveness |
| | `POST /sessions/{id}/finish` | Submit result |
| | `POST /games/{slug}/favorite` and `DELETE` | Favorite toggle |
| | `POST /games/{slug}/rating` | Rate after playing |
| Leaderboards | `GET /leaderboards/xp` | Global XP |
| | `GET /leaderboards/games/{slug}?variant=` | Per-game best |
| | `GET /leaderboards/season` | Current season |
| | `GET /leaderboards/friends` | Referral and challenge connections |
| | `GET /leaderboards/groups/{chat_id}` | Group ranking |
| Check-in | `GET /checkin` and `POST /checkin` | Status and claim |
| Tasks | `GET /tasks`, `POST /tasks/{id}/start`, `POST /tasks/{id}/verify` | Task flow |
| Achievements | `GET /achievements` | All with unlocked state |
| Referrals | `GET /referrals` | Link, counts, rewards |
| Challenges | `POST /challenges`, `GET /challenges/{token}` | Duels |
| Tournaments | `GET /tournaments`, `POST /tournaments/{id}/join` | Events |
| Share | `POST /share/score-card` | Generates the image, returns URL |
| Admin | `/admin/...` | See section 16 |

Common conventions: pagination with opaque cursors, `Idempotency-Key` header accepted on mutating endpoints that can be retried, request IDs in logs, strict input validation.

## 16. Admin Panel API

- Access: admin must authenticate through the same `initData` flow **and** appear in `admin_users` (roles: `admin`, `moderator`).
- Modules:
  - **Games:** import manifests, review `pending`, activate/disable, edit `xp_rate`, caps, `max_score_per_second`.
  - **Tasks:** create/edit/schedule, sponsor association, review queue for `manual` tasks.
  - **Achievements:** CRUD.
  - **Users:** search, view XP ledger, ban/unban, XP adjustment (writes a ledger row and an audit entry).
  - **Flagged runs:** list flagged or rejected sessions, approve (award XP) or confirm (reverse).
  - **Seasons and tournaments:** create, schedule, finalize.
  - **Broadcasts:** compose a message to a segment; preview audience size and estimated send time.
  - **Settings:** edit tunables with validation and change history.
- Every write creates an `audit_log` row. Admin routes get stricter rate limits and optional IP allowlisting.
- The admin UI can start as a minimal web page or even a protected set of bot commands; the API is the same.

## 17. Anti-Cheat and Abuse Control

| Control | Detail |
|---|---|
| Session tokens | Single-use, hashed at rest, tied to the user and game, expire after a maximum duration |
| Server-side timing | `finished_at - started_at` decides minimum play time |
| Plausibility | `max_score`, `max_score_per_second`, per-game variant checks |
| Statistical flags | Scores far above the 99th percentile for a game/variant are held for review |
| Diminishing returns and caps | Per-game daily runs, per-game XP cap, global daily XP cap |
| Rate limits | Redis sliding window per user and IP: session starts, finish calls, task verifies, auth |
| Multi-account signals | Many accounts with the same referrer and zero activity, identical score patterns |
| Task protections | Idempotent claims, periods, caps, smaller rewards for unverifiable tasks |
| Referral protections | Activation required, caps, no self-referral |
| Response to abuse | Flag, hold, reverse via ledger, ban; all actions audited |

Be conservative with automatic bans. Prefer "hold rewards and review" so honest players are not punished by a false positive.

## 18. Observability, Testing, and Security

### Observability
- Structured JSON logs with request IDs and user ids (no tokens, no `initData`).
- Sentry for errors; metrics: request latency (p50/p95/p99), error rate, DB pool usage, queue depth, notification send rate and failures, runs per minute, flagged-run rate.
- Health endpoints: `/healthz` (process up) and `/readyz` (DB and Redis reachable).
- Alerts: error spike, queue backlog, p95 latency, Redis memory, disk space, failed backups.

### Testing
- **Unit:** `initData` validation (good, tampered, stale), XP formula and diminishing returns, level function, streak logic across date boundaries, task period keys, achievement conditions.
- **Integration (real Postgres and Redis through testcontainers):** full flow from auth through session to finish to leaderboard; duplicate and concurrent `finish` calls award XP exactly once; task double-claim attempts; referral activation.
- **Concurrency tests:** many parallel finishes for one user; many users on one game.
- **Load tests (k6 or Locust):** target the mix of score submissions, leaderboard reads, catalog, and check-in at several times expected peak (see section 20).
- **Security tests:** missing/invalid tokens, access to other users' sessions, oversized inputs, injection attempts on string fields.

### Security
- HTTPS only, HSTS, strict CORS limited to the app origin.
- Short JWT lifetime, refresh through fresh `initData`.
- Secrets in environment or a secret manager; rotate if exposed.
- Least-privilege DB user; parameterized queries only (ORM).
- Minimize personal data: store only what Telegram provides and you need (id, names, username, language, photo URL); document retention.
- Provide a simple data-deletion path for users who ask.

## 19. Deployment

### MVP deployment (single server)
- `docker-compose` with services: `api`, `worker`, `postgres`, `redis`, and `caddy` (or Nginx) for TLS and routing. The bot webhook runs inside `api`.
- Environment-specific compose files for staging and production; staging uses a separate bot token.
- CI pipeline: lint, type-check, unit and integration tests, build the image, deploy on merge to `main`; run Alembic migrations as a deploy step with a rollback plan.
- Backups: daily `pg_dump` (or managed backups) to off-server storage, retention at least 14 days, and a **tested restore** before launch.

### Growth path
- Move to managed Postgres; add PgBouncer; run 2 to 3 `api` instances behind a load balancer; keep `worker` separate.
- Add a read replica for admin reports and analytics.
- Put the Mini App frontend and games on a CDN (already planned in Part 1).

## 20. Scalability Plan for 100k Users and 10k DAU

Estimates (assuming about 10 runs per daily user): around 100k score submissions per day, about 1 to 2 per second on average, perhaps 20 to 30 per second at peak; 50 to 100 API requests per second at peak overall. This is comfortable for one tuned Postgres and a couple of API processes.

| Concern | Plan |
|---|---|
| Notification bursts | Queue plus token bucket at about 25 per second; stagger and segment broadcasts; a full 100k broadcast takes about an hour |
| Game file bandwidth | Games on a CDN, immutable URLs; the API never serves game files |
| Leaderboards | Redis sorted sets; top-N cache; Postgres rebuild path |
| Table growth | Index design from section 6; plan monthly partitioning for `scores` and `xp_events` and archive old partitions |
| DB connections | PgBouncer once there are multiple API instances |
| Hot rows | Per-user row locks only; no global counters updated on every request |
| Spikes (task announcements, tournament ends) | Cache catalog and task lists for 30 to 60 seconds, idempotent endpoints, rate limits |
| Idempotency | Ledger keys and unique constraints make retries safe |
| Failure recovery | Resumable notification jobs, retries with backoff, rebuildable Redis |

Habits: load test before launch, watch the metrics in section 18, keep tunables in the database, and scale out only when metrics show a need.

## 21. Step-by-Step Implementation Phases

Rough effort for one developer, part-time. "Needs G#" refers to phases in `01-game-adaptation-plan.md`.

### Phase B0: Foundations (2 to 3 days)
1. Create the repo and layout (section 3), Dockerfile, `docker-compose.yml`, `.env.example`.
2. Set up Postgres, Redis, Alembic, logging, Sentry, health endpoints, CI.
3. Create the bot with BotFather; set menu button and Mini App; set the webhook with a secret.
4. Implement `validate_init_data` with unit tests (valid, tampered, stale).
5. Implement `POST /auth/telegram`, JWT issue and verification, `GET /me`.
6. Migrations for `users`, `games`, `game_sessions`, `scores`, `xp_events`, `settings`.
7. Deploy a staging environment over HTTPS and open a hello-world Mini App that shows the real user.

**Done when:** opening the Mini App from Telegram returns your profile from your own backend on staging.

### Phase B1: Core loop (1 to 2 weeks), needs G1 (2048)
1. Manifest import job and `GET /games`, `GET /games/{slug}`.
2. Sessions: `POST /games/{slug}/sessions`, token hashing, expiry.
3. Finish endpoint with all validation rules (section 8.3) inside a transaction.
4. XP service: formula, diminishing returns, caps, level function, ledger insert with idempotency keys.
5. Redis leaderboards for games and global XP; `GET /leaderboards/...` endpoints; rebuild job.
6. Rate limiting middleware.
7. Tests: finish idempotency, concurrency, plausibility checks, XP math.
8. Frontend integration with 2048 and the test host results.

**Done when:** a player completes a 2048 run in Telegram, sees XP and rank, and the same request retried gives no extra XP.

### Phase B2: Retention (1 week), needs G2
1. Check-in and streaks endpoints and logic; reminder job.
2. Achievements model, evaluator, and first ~10 achievements.
3. Profile endpoints: XP history, level progress.
4. Add the remaining adapted games to the catalog and tune `xp_rate` using real data.
5. Settings table editing through admin endpoints (basic).

**Done when:** players have a daily reason to return and see progression.

### Phase B3: Tasks and notifications (1 to 2 weeks)
1. Tasks tables and engine; handlers for `join_channel`, `play_game`, `invite_friends`, `open_link`, `custom`.
2. `getChatMember` verification queue with throttling.
3. Notification outbox, worker, token bucket, error handling (`429`, `403`), localized templates.
4. Admin API: tasks CRUD, manual review queue, games activation, users and ban/unban, flagged runs, audit log.
5. Admin UI (minimal).
6. Strengthen anti-cheat: statistical flags, per-IP limits, holds.

**Done when:** an admin creates a task, users are notified and complete it, and XP is awarded without developer involvement.

### Phase B4: Social (1 to 2 weeks)
1. Referrals with activation and caps.
2. Challenges and sharing links; `challenge_beaten` notifications.
3. Friends and group leaderboards; `/top` in groups; `my_chat_member` handling.
4. Score-card generation and share endpoint (with caching).
5. Favorites, recently played, categories, ratings, trending job.

**Done when:** users invite friends, challenge each other, and see group rankings.

### Phase B5: Events and polish (2+ weeks)
1. Seasons: season id on ledger rows, season leaderboard, end-of-season job.
2. Daily/weekly challenges with rotation job.
3. Tournaments.
4. Multi-language: bot templates and API-provided localized strings (Afaan Oromo, Amharic, English).
5. Sponsored tasks and sponsor reports.
6. Monthly partitioning plan for `scores` and `xp_events`; archive job.
7. Analytics queries and dashboards (DAU, retention, runs per game, task completion, referral conversion).

### Phase B6: Launch readiness (1 week)
1. Load test (k6/Locust) at several times expected peak; fix bottlenecks.
2. Security review: auth paths, admin access, rate limits, secrets, CORS, headers.
3. Backups with a tested restore; monitoring alerts configured.
4. Privacy notice, terms, data-deletion path.
5. Soft launch with a small group; watch flagged runs, error rates, and notification delivery; tune XP and task rewards.
6. Public launch and iterate on metrics.

## 22. Combined Timeline (rough)

| Week | Games (Part 1) | Backend (Part 2) |
|---|---|---|
| 1 | G0, start G1 (2048) | B0 foundations |
| 2 | Finish G1 | Start B1 core loop |
| 3 | G2 (wavde set) | Finish B1 |
| 4 | Finish G2, start G3 | B2 retention |
| 5 | G3 (remaining games) | B3 tasks and notifications |
| 6 | G4 QA and performance | Finish B3, admin |
| 7 | G5 publish | B4 social |
| 8+ | Fixes and tuning | B5 events, B6 launch readiness |

Dependencies: B1 needs the bridge and at least 2048 (G0 and G1). B2 benefits from G2 for score balance data. B3's Wordle daily flow needs the server seed endpoint from B1.

## 23. Risks and Open Decisions

| Item | Note |
|---|---|
| Time zones | UTC day for streaks and dailies in the MVP; revisit per-user time zones after launch |
| Score trust | Client-reported scores are never fully trustworthy; plausibility checks and caps limit damage; consider server-side replays for a few simple games later |
| Notification volume | Telegram limits and user annoyance; keep caps and an easy opt-out |
| Task farming | Idempotency, caps, smaller rewards for unverifiable tasks, manual review |
| Telegram API changes | Re-check `initData` validation, share methods, and limits against current docs when implementing |
| GPL game (Hextris) | Handled in Part 1; backend is unaffected |
| Single-server risk | Backups and a documented restore; move to managed Postgres when the audience grows |
| Scope creep | Ship Milestones B0 to B3 first; tournaments, sponsors, and seasons come after real usage data |

## 24. Master Checklist

- [x] B0: repo layout, config, DB/Redis setup, `initData` auth + JWT, `/me`, migrations, health endpoints — all built and tested against a real local Postgres. **Not done**: the actual bot (no aiogram handlers, `app/bot/` is empty), CI pipeline, and staging deployment (no hosting/domain, no real `BOT_TOKEN`).
- [x] B1: manifest import job, `GET /games`/`GET /games/{slug}`, sessions + finish endpoint (every plan section 8.3 validation rule), XP ledger with idempotency, Redis leaderboards, rate limiting — all built and verified end-to-end (231 tests passing, see `server/README.md`). **Caveat**: no real Redis exists in the environment this was built in (no sudo, no docker network access) — runs against `fakeredis` by default; untested against a real Redis server. No leaderboard rebuild job yet.
- [x] B2: check-in + streaks (with freeze/reset logic and the 7th-day XP bonus), achievements (event-driven evaluator, 10 seeded achievements, unlock-once guarantee), enriched profile (`/me`, `/me/xp-history` cursor pagination, `/achievements`), basic admin API (bootstrap from `ADMIN_TELEGRAM_IDS`, game status/xp_rate editing, settings get/put, audit log) — all built and verified end-to-end (255 tests passing). **Used the new admin API for real** to flip all 10 imported games from `pending` to `active` — not raw SQL. **Not done**: a real admin UI (API only), the streak-reminder job (plan section 14.3, needs the notification worker from B3).
- [x] B3: task engine (6 handler types — `play_game`/`daily_open`/`open_link`/`custom` fully working; `join_channel` implemented+unit-tested but unverified against a real bot; `invite_friends` simplified, no activation system yet), notification outbox+worker+templates (polling-based, not ARQ — see README), admin extensions (task CRUD/review queue, user search/ban/XP-adjust, flagged-score approve/reject), anti-cheat upgrades (statistical-outlier flagging, per-user+per-IP rate limiting) — all built and verified end-to-end (279 tests passing, see `server/README.md`). **Not done**: a real admin UI (API only, as the plan itself allows), the `getChatMember` verification queue+throttle (direct call instead), localized notification templates (English only, correctly deferred to B5).
- [x] B4: referral activation + daily/total reward caps, friend duel challenges (create/beat/reward, race-safe), favorites + ratings + category filter + trending job, the friends leaderboard (Postgres referral/challenge graph, not Redis), score-card image generation (Pillow, disk-cached, served via a static mount) — all built and verified end-to-end (302 tests passing, see `server/README.md`). Also fixed the `invite_friends` task (B3) to require an activated referral rather than just a signup, now that activation exists. **Not done**: group boards (`GET /leaderboards/groups/{chat_id}`) — needs `my_chat_member` tracking, which needs the bot (still not built, see B0).
- [x] B5: seasons (season_id on every XP ledger row, Postgres season leaderboard, end-of-season finalize job that freezes results/pays rank XP/starts the next season), tournaments (join, best_score/sum_top_n rules, closing job), daily/weekly challenge rotation (reuses the task engine), sponsors (real FK, per-sponsor completion/XP report), multi-language notification templates (en/am/om), one admin analytics endpoint (DAU/retention/runs-per-game/task-completion/referral-conversion) — all built and verified end-to-end (321 tests passing, see `server/README.md`). **Not done**: partitioning (designed in the README, not implemented — genuinely not needed yet at near-zero table sizes); "badges" as a concept separate from the existing achievements system (seasons/tournaments pay XP only); am/om translation review by a native speaker; am/om *content* for games/achievements/tasks (a content task, not code).
- [x] B6: load test (found and fixed a real bottleneck — a single `uvicorn` process can't hit the plan's own 50-100 req/s peak target; fixed with a wider DB pool + `--workers 4`, confirmed ~108 req/s after), security review (fixed a silent-exception-swallowing bug, two missing rate limits, a null-byte crash, added a production-secret startup guard and security headers), backups tested (real `pg_dump`/`pg_restore` round-trip against the dev DB, row counts and content verified), data-deletion path (`DELETE /me`), CI pipeline (`.github/workflows/backend-ci.yml`), privacy/terms drafts (`PRIVACY.md`/`TERMS.md`, explicitly marked non-legal) — all built and verified for real (339 tests passing, see `server/README.md`'s B6 section for the full writeup). **Not done, needs real infrastructure**: an actual staging/production deployment, live monitoring/alerting wired to a real account, off-server backup storage, soft launch, public launch. **Not verified locally**: `ruff check .` passing clean (couldn't install `ruff` in this sandbox — see README) and the CI workflow actually running (no GitHub Actions access from here).

See `server/README.md` for exactly what was verified vs. not in this pass.
