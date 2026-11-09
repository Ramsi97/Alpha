# AlphaGo web-frontend

The Telegram Mini App itself — React + TypeScript + Vite. Talks to `../../server/` over its `/api/v1` HTTP API and embeds the games in `../../games/` via their `postMessage` bridge contract (`games/_shared/alphago-bridge.js`).

## Status

A real, working shell, not a mockup: login, catalog, gameplay (full session lifecycle), leaderboards, tasks, and profile are all wired to the live backend and were smoke-tested end-to-end in a browser against a real local Postgres-backed API. What's deliberately not here yet:

- **Telegram-only features that need a real bot/device**: this was only tested in a plain Chrome tab via the dev-sim login (see below), never inside real Telegram. Haptics, the native BackButton, and theme param propagation call the real Telegram Web App SDK but are unverified against an actual Telegram client.
- **Friend duel challenges, favorites toggling on the game-detail level, score-card sharing, referral deep-link UI, xp-history view, achievements list UI** — backend endpoints exist (see `server/README.md`) but have no screen here yet.
- Polished visual design — this is a functional shell (system fonts, emoji nav icons, Telegram theme variables), not a final UI pass.
- Route-based deep linking (e.g. opening a specific game from a Telegram deep link's `start_param`) — `getStartParam()` exists in `src/lib/telegram.ts` but nothing consumes it yet.

## Running it locally

You need all three pieces up at once:

```bash
# 1. Backend (from server/, with its own .venv — see server/README.md)
cd ../../server && .venv/bin/uvicorn app.main:app --port 8000

# 2. Games, served statically (from games/)
cd ../../games && python3 -m http.server 8731

# 3. This app
cp .env.example .env.local   # only needed once
npm run dev
```

Open the printed `http://localhost:5173`. The backend's default CORS (`APP_ORIGIN`) and games origin (`GAMES_ORIGIN`) already match these ports — see `server/.env.example`.

### Logging in without real Telegram

A Telegram Mini App only ever receives a valid `initData` string from the real Telegram client. For local development, `src/lib/telegram.ts`'s `buildDevInitData()` signs a synthetic one client-side using the backend's own *public, documented* dev placeholder bot token (`app/core/config.py`'s `bot_token` default, `"dev-placeholder-bot-token"`) — not a secret or a bypass of real auth, just a way to exercise the real `POST /auth/telegram` HMAC-validation path without Telegram. This only runs when `import.meta.env.DEV` is true (never in a production build) and only when the page wasn't actually opened by Telegram (`window.Telegram.WebApp.initData` empty). See `src/state/AuthContext.tsx`.

## Architecture

- `src/lib/telegram.ts` — Telegram Web App SDK wrapper (loaded via `<script>` in `index.html`, not npm, per Telegram's own docs) + the dev-sim login helper above.
- `src/lib/api.ts` — typed fetch client, bearer-token auth, token persisted in `localStorage`.
- `src/lib/types.ts` — hand-written mirror of `server/app/schemas/*.py` response shapes. **Keep these in sync by hand** — there's no shared codegen between the two repos.
- `src/state/AuthContext.tsx` — owns the login flow and the current `UserOut`; `useAuth()` exposes `user`, `refreshMe()`, `logout()`.
- `src/screens/` — one per bottom-nav tab (`CatalogScreen`, `LeaderboardScreen`, `TasksScreen`, `ProfileScreen`) plus `GameScreen`, which is pushed on top when a game is opened.
- `src/App.tsx` — the whole router: a `view` + optional `playingSlug` in component state, no routing library. Deliberately simple for a four-tab app; revisit if deep-linking is added.

### The game-hosting bridge (`GameScreen.tsx`)

This is the one piece worth understanding before touching it — it's the host side of `games/_tools/test-host.html`'s reference implementation, talking to whatever untrusted game is loaded in the sandboxed iframe:

1. On mount: `POST /games/{slug}/sessions` (gets a `session_id` + anti-cheat `token` + `seed`), then render `<iframe sandbox="allow-scripts allow-same-origin" src={entry_url}>`.
2. Listen for `postMessage` from the iframe. On `"ready"`, reply with `{type: "start", seed, variant, lang, theme}` — this is the point at which the game actually begins.
3. On `"gameover"`, call `POST /sessions/{id}/finish` with the reported score and show the result overlay (XP, level, rank, new achievements). Guarded by a ref so a double `"gameover"` can't double-submit.
4. A 20s heartbeat (`POST /sessions/{id}/heartbeat`) runs while playing, independent of the final score report.

Verified against the real `dummy` fixture game (`games/dummy/`, normally excluded from the catalog — see `games/README.md`) to force a deterministic win/lose without actually playing a full round; temporarily activated in the dev DB for that one test, then set back to `status: "pending"` afterward.

## Known gaps worth flagging

- `UserOut` doesn't expose `notifications_enabled` back to the client (see `server/app/schemas/user.py`), so `ProfileScreen`'s toggle is write-only — it can turn notifications off but can't show whether they're currently on.
- Favoriting is only exposed from the catalog grid, not reflected on a (non-existent) game detail screen.
- No error boundary — an unhandled render error anywhere blanks the screen instead of showing a fallback.
