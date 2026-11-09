# AlphaGo, Part 1: Game Adaptation Plan

Companion files: `02-backend-plan.md` (backend) and `alphago-project-plan.md` (original overview).
Where this file differs from the overview, **this file wins** (the overview assumed provider games and a play-time mode; the final decision is self-hosted open-source games with score reporting).

---

## 1. Goal and Scope

Take up to 10 open-source HTML5 mini games and turn them into a consistent, ad-free, mobile-friendly game set that:

1. Runs inside an iframe in the Telegram Mini App.
2. Reports a score to the host app through one shared bridge script.
3. Looks right in Telegram's light and dark themes.
4. Loads fast on low-end phones and slow connections.
5. Is legally clean (license and credits tracked for every game).

**Out of scope for this file:** the server side (sessions, XP, leaderboards, anti-cheat). That is in `02-backend-plan.md`. The game side only needs to report honest scores and respect the contract below.

## 2. Decisions Already Made

| Decision | Choice |
|---|---|
| Game source | Open-source HTML5 games, self-hosted (no provider catalogs, no ads) |
| Catalog size | At most 10 games, different categories |
| Score delivery | Game calls the shared bridge (`postMessage`); host forwards to the backend with a session token the game never sees |
| XP | Hybrid: raw score kept per game for leaderboards, converted to XP with a per-game rate |
| Economy | None (no shop, coins, or payments) |

## 3. Game Lineup

Licenses were checked in each repo's README or listing. **Game quality, mobile behavior, and asset licenses (images, sounds, fonts) still need to be verified per game** (see section 6 and the vetting checklist).

| # | Game | Category | Source | Code license | Score definition | Effort | Main risk |
|---|---|---|---|---|---|---|---|
| 1 | 2048 | Number puzzle | gabrielecirulli/2048 | MIT | In-game score | Low | Remove local best-score storage |
| 2 | Lights Out | Puzzle | wavde/games | MIT | Par-based on moves | Low | Check generator for fairness |
| 3 | Mini Sudoku | Logic | wavde/games (alt: minisudoku.github.io) | MIT | Time + penalties | Medium | Puzzle uniqueness, daily seed |
| 4 | Minesweeper | Logic | wavde/games | MIT | Time per difficulty (wins only) | Medium | Long-press flag UX |
| 5 | 0hh1 | Binary logic | Q42/0hh1 | MIT | Grid size + time | Medium | Older codebase, check assets |
| 6 | Memory Match | Memory | wavde/games | MIT | Moves + time | Low | Grid size variants |
| 7 | Connect Four | Strategy vs AI | wavde/games | MIT | Win-based with move bonus | Medium | Verify AI exists and difficulty |
| 8 | Wordle-style | Word | stonedhawk/wordle-clone (rewrite) | MIT | Guesses used | High | In-browser Babel is slow; word list source; daily word must come from server |
| 9 | Snake | Arcade | aashish0613/javascript-games or own build | MIT | Food eaten x 10 | Low | Beginner-quality code; consider writing your own |
| 10 | Hextris | Reflex arcade | Hextris/hextris | **GPLv3** | In-game score | Medium | GPL obligations (see section 11) |

**Do not use:** Clumsy Bird (Flappy-style art is an IP risk) and the wavde "Tango / Queens / Zip / Patches" games unless you verify they are not clones of another company's puzzles.

**Fallback if Hextris is dropped:** Breakout (MIT version in the GameHub repo).

## 4. Repository Layout and Hosting

```
games/
  _shared/
    alphago-bridge.js       # same file included by every game
    theme.css               # Telegram theme variables + base mobile styles
    i18n-helper.js          # tiny helper: t("key") from a per-game strings object
  _tools/
    test-host.html          # local test host (section 9)
    validate-manifest.mjs   # checks game.json files against the schema
  2048/
    index.html
    game.js
    style.css
    thumb.png
    game.json               # manifest (section 5.3)
    LICENSE                 # original license, unchanged
    CREDITS.md              # source repo, author, what you changed
  minesweeper/ ...
```

**Hosting**
- Serve games from a **separate origin** (for example `games.yourdomain.com`), not the Mini App's origin. This isolates third-party code from your app and its cookies/tokens.
- Put them on static hosting behind a CDN (Cloudflare Pages or similar).
- **Versioned, immutable URLs:** `/{slug}/{version}/index.html` with `Cache-Control: public, max-age=31536000, immutable`. A new game version means a new path, so players never run a stale half-updated game.
- Security headers for the games origin:
  - `Content-Security-Policy: default-src 'self'; img-src 'self' data:; connect-src 'none'; frame-ancestors https://app.yourdomain.com` (adjust once you know what each game needs). `connect-src 'none'` stops games from calling any external server, which blocks tracking and data leaks.
  - `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`.

## 5. The Host-Game Contract

### 5.1 Messages

All messages are plain objects sent with `postMessage`.

**Game to host**

| type | fields | when |
|---|---|---|
| `ready` | none | Game finished loading and can start |
| `score` | `value` | Optional live score update (for display only; never used for rewards) |
| `gameover` | `score`, `variant?`, `meta?` | A run ended (win or loss). This is the only message that can produce XP |
| `error` | `message` | Unrecoverable game error |

**Host to game**

| type | fields | when |
|---|---|---|
| `start` | `variant?`, `seed?`, `lang`, `theme` | Host created a server session and the run may begin |
| `pause` / `resume` | none | App hidden/visible, Telegram closing, or user opened a menu |
| `theme` | `params` | Telegram theme changed |

`source` fields (`alphago-game` / `alphago-host`) tag every message so unrelated messages are ignored.

### 5.2 The shared bridge (`_shared/alphago-bridge.js`)

```js
(function () {
  const HOST_ORIGIN = window.__ALPHAGO_HOST_ORIGIN__ || "*"; // inject real origin at build/deploy time
  const send = (msg) =>
    parent.postMessage({ source: "alphago-game", ...msg }, HOST_ORIGIN);

  window.addEventListener("message", (e) => {
    if (HOST_ORIGIN !== "*" && e.origin !== HOST_ORIGIN) return;
    if (e.source !== parent) return;
    const d = e.data || {};
    if (d.source !== "alphago-host") return;
    window.dispatchEvent(new CustomEvent("alphago:" + d.type, { detail: d }));
  });

  window.AlphaGo = {
    ready:    ()            => send({ type: "ready" }),
    score:    (value)       => send({ type: "score", value }),
    gameOver: (score, opts) => send({ type: "gameover", score, ...(opts || {}) }),
    error:    (message)     => send({ type: "error", message }),
  };
})();
```

Rules for game code:
- Call `AlphaGo.ready()` after load; then wait for the `alphago:start` event before starting a run.
- Call `AlphaGo.gameOver(score, { variant, meta })` exactly once per run.
- Listen for `alphago:pause` and `alphago:resume` and actually pause timers and animation loops.
- Never read or send any token, user id, or network data. The game only knows its own score.

### 5.3 Manifest (`game.json`)

One manifest per game. A script validates it, and the backend's game-import job reads it to create or update rows in the `games` table.

```json
{
  "slug": "minesweeper",
  "version": "1.0.0",
  "title": { "en": "Minesweeper" },
  "description": { "en": "Clear the board without hitting a mine." },
  "category": "logic",
  "thumbnail": "thumb.png",
  "entry": "index.html",
  "orientation": "portrait",
  "variants": ["easy", "medium", "hard"],
  "score": {
    "mode": "bridge",
    "higher_is_better": true,
    "max_score": 3000,
    "min_play_seconds": 8,
    "max_score_per_second": 100
  },
  "xp": { "rate": 0.05, "max_per_run": 150 },
  "license": {
    "code": "MIT",
    "assets": "MIT",
    "author": "Original author name",
    "source_url": "https://github.com/..."
  },
  "size_kb": 420,
  "status": "pending"
}
```

**Mapping to the database (`games` table):** `slug`, `version`, `title`, `description`, `category`, `thumbnail`, `entry`, `variants`, `max_score`, `min_play_seconds`, `max_score_per_second`, `xp_rate`, `max_xp_per_run`, `license_*`, `size_kb`, `status`. `status` starts as `pending` and an admin sets it to `active` after review.

**Variants** (difficulty or board size) get **separate leaderboards**, so an easy minesweeper time never competes with a hard one.

## 6. Standard Adaptation Checklist (apply to every game)

1. **Import cleanly:** copy the source into `games/<slug>/`, keep the original `LICENSE` file and copyright headers, create `CREDITS.md`.
2. **Remove external requests:** analytics, ad scripts, CDN libraries, remote fonts, social buttons. Bundle needed libraries locally. Verify in the browser's network tab that nothing leaves the games origin.
3. **Remove or neutralize local persistence** (best score, saved state in `localStorage`). The server owns scores. If mid-game save is useful (for example sudoku), wrap storage access in try/catch.
4. **Add the bridge:** include `alphago-bridge.js`, call `ready()`, wait for `start`, call `gameOver()` at the end of a run.
5. **Define the score** (section 7) and decide the variants.
6. **Restart flow:** "Play again" must end the current session and request a new one (emit a `gameover` first if the run was completed, or send nothing if abandoned). The host decides when to create a new session; the game just waits for `start` again.
7. **Pause support:** pause timers and animation on `alphago:pause`.
8. **Mobile and WebView:**
   - Touch controls (no hover-only UI), minimum 44px tap targets.
   - `viewport` meta with `viewport-fit=cover` and safe-area padding.
   - Disable page scroll, pinch zoom, and text selection during play (`touch-action`, `user-select`).
   - Works in portrait; handles resize and orientation change.
9. **Theme:** use CSS variables from `theme.css` (mapped from Telegram `themeParams`); no hard-coded white or black backgrounds.
10. **Strings for translation:** move all visible text into one `STRINGS` object per game with keys, defaulting to English. Afaan Oromo and Amharic are added later by filling the same keys.
11. **Performance:** total size at most 2 MB (target under 1 MB), compress images (WebP), minify JS/CSS, avoid heavy per-frame allocations in arcade games.
12. **Accessibility basics:** readable contrast, no flashing effects, optional sound with a mute toggle (default muted or low).
13. **Add the manifest and thumbnail** and run `validate-manifest.mjs`.
14. **Playtest:** at least 10 runs on a real low-end Android phone inside Telegram.

### Definition of Done (per game)

- [ ] License verified for code **and** assets; `CREDITS.md` complete
- [ ] No network requests outside the games origin
- [ ] Bridge works in the test host (`ready`, `start`, `gameover` seen once per run)
- [ ] Pause/resume works
- [ ] Looks correct in light and dark themes
- [ ] Playable one-handed on a small phone; no scroll or zoom glitches
- [ ] Under size budget; loads in under 5 seconds on throttled slow 3G
- [ ] Manifest valid and values tuned (section 7)

## 7. Score Definitions and Starting Values

All numbers are **starting points to tune after playtesting**. Principle: a decent run in any game should be worth roughly **50 to 150 XP**, so no single game dominates progression. Set `xp.rate = target_xp / typical_score`. Losses that are not meaningful runs report a score of 0 (the server grants no XP for 0).

| Game | Raw metric | Score formula | Variants | max_score | min_play_seconds | xp.rate (start) |
|---|---|---|---|---|---|---|
| 2048 | In-game score | `score` | none (4x4) | 500000 | 20 | 0.01 (20k pts = 200 XP; cap per run 300) |
| Minesweeper | Time on a **win** | `base * max(0.2, 1 - seconds/target)`; base 300/700/1500, target 120/400/900 s | easy/medium/hard | 1500 | 8 | 0.08 |
| Memory Match | Moves, time | `size_mult * max(0, 1000 - 10*moves - 2*seconds)`; size_mult 1/2/3 for 4x4/6x6/8x8 | 4x4/6x6/8x8 | 3000 | 10 | 0.04 |
| Mini Sudoku | Time, mistakes, hints | `diff_mult * max(100, 1000 - 2*seconds - 50*mistakes - 100*hints)` | easy/medium/hard | 3000 | 20 | 0.04 |
| Lights Out | Moves vs par | `max(0, 1000 - 25 * max(0, moves - par))`, par from the generator | by grid size | 1000 | 5 | 0.1 |
| 0hh1 | Grid size, time | `size^2 * 10 + max(0, 300 - seconds)` | 4x4/6x6/8x8 | 1000 | 10 | 0.1 |
| Connect Four | Result, moves | win: `500 + (42 - moves) * 10`; draw: 100; loss: 0; times difficulty mult | easy/medium/hard | 1500 | 15 | 0.08 |
| Wordle-style | Guesses used on a win | `(7 - guesses) * 150`; loss 0; daily puzzle once per day | none | 900 | 10 | 0.12 |
| Snake | Food eaten | `food * 10` | none | 5000 | 15 | 0.03 |
| Hextris | In-game score | `score` | none | 100000 | 15 | 0.004 |

Notes
- `max_score_per_second` in the manifest is what the backend uses for plausibility checks. Set it from real playtest data: take the best human run you can achieve, then add a 2x to 3x margin.
- Time-based scores can be gamed by a client that lies about time. The backend also measures the real server-side duration of the session and refuses scores whose claimed play time is impossible (see backend plan).
- For daily puzzles (Wordle-style, Mini Sudoku daily), the **server supplies the seed or word** through the `start` message, never the player's device clock.

## 8. Per-Game Adaptation Notes

**2048 (pilot game)**
- Find where the game manager detects `over` and `won`; call `AlphaGo.gameOver(score)` at game over, or when the player chooses not to continue after reaching 2048.
- Remove the local best-score storage and the "keep playing" persistence.
- Replace the intro and footer text with your own strings and credits link.
- Check swipe handling works inside the iframe without page scroll.

**Minesweeper (wavde)**
- Report only on **wins** (loss = score 0, still send `gameover` so the host can end the session).
- Variants map to board sizes; send `variant` with the result.
- Long-press to flag: make the delay and haptic feedback feel right; avoid triggering the system context menu.

**Memory Match (wavde)**
- Count moves and time inside the game; send both in `meta` for logging, only `score` is used for rewards.
- Grid size is the variant.

**Mini Sudoku (wavde or minisudoku)**
- Use a server `seed` from the `start` message so daily puzzles are identical for everyone and cannot be re-rolled.
- Track mistakes and hints for the score formula.

**Lights Out (wavde)**
- Make sure generated boards are solvable and compute `par` (minimum or near-minimum moves).

**0hh1 (Q42)**
- Older codebase: check dependencies (jQuery or similar) are bundled locally.
- The score depends on grid size and time; report each completed puzzle as a run, or a streak of puzzles as one run (decide in playtesting).

**Connect Four (wavde)**
- Verify an AI opponent exists; if not, add a simple minimax with depth by difficulty.
- Win gives XP; a quit mid-game gives nothing.

**Wordle-style (rewrite)**
- Rewrite in vanilla JS (no in-browser Babel, no React CDN).
- The daily answer must **not** ship inside the client in a way that reveals it. Options: backend returns a result per guess, or a hashed answer with the word list validated client-side. The simplest safe path: the host passes the word list index through `start`, and you accept that a determined cheater can inspect it, while the backend limits the reward to one win per day.
- Check the word list's license separately from the game code.

**Snake**
- If the found code is weak, write your own (about 100 lines of canvas). Use grid-based movement, swipe controls, and speed increases every N foods.

**Hextris (GPLv3)**
- Keep it clearly separate (own folder, own license text, prominent source link).
- Add the bridge as a small separate file; see section 11 before shipping.

## 9. Test Host and QA

### 9.1 Local test host (`_tools/test-host.html`)

A simple page that:
- Lists all games from their `game.json` files.
- Embeds the chosen game in an iframe with the same `sandbox` attributes planned for production.
- Sends `start` (with fake `seed`, `lang`, `theme`) when it receives `ready`.
- Logs every message received from the game with a timestamp, and flags problems: no `ready` within 5 seconds, `gameover` sent twice, `score` above `max_score`, a message with a wrong `source`.
- Buttons to send `pause`, `resume`, and switch theme.

### 9.2 Production iframe settings (decided here, implemented in the Mini App frontend)

- Origin: `https://games.yourdomain.com`.
- `sandbox="allow-scripts allow-same-origin"`. This is acceptable because the games origin differs from the app origin, so the games cannot reach the app's storage or cookies.
- Host verifies `event.origin === GAMES_ORIGIN` **and** `event.source === iframe.contentWindow` before accepting any message.
- Host ignores any message type not listed in section 5.1.

### 9.3 QA matrix

| Area | Cases |
|---|---|
| Devices | Low-end Android (2 GB RAM), mid Android, iPhone, Telegram Desktop |
| Telegram | Android, iOS, Desktop, Web clients |
| Network | Fast, throttled slow 3G, offline after first load (if service worker is used) |
| Themes | Light, dark, theme switch during play |
| Lifecycle | App sent to background, call interrupts, close and reopen, rapid restart |
| Input | Touch, swipe, long-press, multi-touch, keyboard (desktop) |
| Bridge | One `gameover` per run, `pause` respected, no messages after unload |

### 9.4 Performance budgets

- Total game size: at most 2 MB (target under 1 MB).
- First meaningful load on slow 3G: under 5 seconds.
- Arcade games: steady frame rate on a low-end phone, no long garbage-collection pauses.
- Memory: no growth over a 5-minute session.

## 10. Caching and Offline (optional but recommended)

- Immutable, versioned URLs (section 4) already give instant repeat loads.
- Optional service worker per game to pre-cache its files so it works with a flaky connection. Keep it simple: cache-first for game files, never cache the host's API calls.
- Show a clear "loading game" state in the host while waiting for `ready`, and a retry button if it does not arrive in 10 seconds.

## 11. Licensing, Credits, and GPL Handling

- **Per game:** record code license, asset license, author, and source URL in `game.json` and `CREDITS.md`.
- **Attribution in the app:** show "Credits" on each game's info screen (author, license, link to source).
- **MIT:** keep the copyright notice and license text with the game files.
- **Assets:** images, fonts, and audio may have different licenses (CC-BY, CC-BY-NC, or none). Replace any asset whose license is unclear, or remove it. "NC" (non-commercial) assets are a problem if you ever monetize.
- **GPLv3 (Hextris):** distributing it (serving it to players' browsers counts) means you must provide the corresponding source of your modified version under GPLv3, with the license text. Keep the modification small and separate, publish your modified source in a public repo, and link it from the credits screen. Whether your host app counts as a "combined work" with an embedded GPL iframe is a legal question; the iframe boundary and message-only communication make a separate-program argument reasonable, but get proper advice before launch, or swap in an MIT Breakout instead.
- Keep a `LICENSES.md` index at the repo root listing every game and its license status.

## 12. Step-by-Step Phases

Rough effort for one developer working part-time. Backend phases that depend on these are shown in `02-backend-plan.md`.

### Phase G0: Setup (0.5 to 1 day)
1. Create the `games/` repo with the layout in section 4.
2. Write `alphago-bridge.js`, `theme.css`, `i18n-helper.js`.
3. Write the manifest schema and `validate-manifest.mjs`.
4. Build `test-host.html`.
5. Set up static hosting for the games origin with the security headers.

**Done when:** a dummy game in the repo sends `ready` and `gameover` and the test host logs them correctly.

### Phase G1: Pilot game, 2048 (1 to 2 days)
1. Import 2048 with its license; create `CREDITS.md`.
2. Apply the full checklist (section 6).
3. Tune manifest values; run the QA matrix on real devices.
4. Write down every problem you hit as notes for the other games.

**Done when:** 2048 passes the definition of done and can be embedded by the real Mini App.
**Unblocks:** backend Phase B1 (core loop) can use 2048 immediately.

### Phase G2: The wavde/games set (3 to 4 days)
1. Import the repo once; split out Minesweeper, Memory Match, Mini Sudoku, Lights Out, Connect Four into their own folders.
2. Build a shared layout and theme for them, since they likely share structure.
3. Apply the checklist to each; define score formulas and variants.
4. Playtest each for score ranges and tune `max_score`, `min_play_seconds`, `xp.rate`.

**Done when:** five games pass the definition of done.

### Phase G3: Remaining games (3 to 5 days)
1. 0hh1: import, bundle dependencies, define scoring.
2. Snake: write or adapt; add swipe controls.
3. Wordle-style: rewrite in vanilla JS; implement the server-driven daily word flow with the backend team (you).
4. Hextris: import, add the bridge, set up GPL compliance (or swap for Breakout).

**Done when:** all 10 games pass the definition of done (or you ship with 9 and keep the 10th for later).

### Phase G4: QA and performance (2 to 3 days)
1. Run the full QA matrix across devices and Telegram clients.
2. Measure size and load time; compress and trim.
3. Review all `CREDITS.md` files and the root `LICENSES.md`.
4. Tune score formulas using real playtest data so XP per run is balanced across games.

**Done when:** every game meets the performance budgets and the license review is complete.

### Phase G5: Publish (1 day)
1. Deploy each game to its versioned immutable path.
2. Finalize manifests with real sizes and URLs; set `status` to `pending`.
3. Backend import job reads manifests and creates `games` rows; admin reviews and activates each game.
4. Smoke test every game from inside the real Mini App on a phone.

**Done when:** all intended games are `active` in the catalog and playable end to end.

## 13. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Unclear asset licenses | Audit assets per game; replace anything doubtful |
| Games too heavy for low-end phones | Size budgets, WebP, minify, test on a cheap phone early |
| Time-based scores easy to fake | Server measures session duration; plausibility checks; caps per run |
| Score balance across games | Tune `xp.rate` from playtest data; cap XP per run and per day |
| GPL obligations (Hextris) | Keep separate and published, or swap for Breakout |
| Embedded third-party code | Separate origin, CSP with `connect-src 'none'`, origin and source checks |
| Daily puzzle spoilers | Server-provided seed or answer flow; one reward per day |
| Maintenance burden of 10 forks | Shared bridge and theme; keep changes small; document each game's changes in `CREDITS.md` |

## 14. Master Checklist

- [x] G0: repo, bridge, theme, manifest validator, test host, games origin (games origin is still only local-dev, see games/README.md)
- [x] G1: 2048 done
- [x] G2: Minesweeper, Memory Match, Mini Sudoku, Lights Out, Connect Four done
- [x] G3: 0hh1, Snake, Wordle-style, Breakout (Hextris swapped for its own named fallback, see games/breakout/CREDITS.md) done
- [ ] G4: QA matrix, performance, license review, score balance — manifests/validator/syntax checks done; real-device QA, license verification (2048 font, 0hh1 font+provenance), and score-formula tuning from real playtest data are NOT done (no browser/device available in the environment these were built in)
- [ ] G5: deployed, manifests imported, games activated, smoke tested in Telegram — not started; no real hosting/domain set up yet

See games/NOTES-G1.md, games/NOTES-G2.md, games/NOTES-G3.md for what was
verified vs. what still needs a human + real device/browser pass before
any of this ships.
