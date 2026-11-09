# Phase G1 notes (2048 pilot) — for adapting the rest of the catalog

Lessons from adapting `games/2048/`, to reuse for G2/G3.

## Patterns that worked, reuse as-is

- **Gate every run on `alphago:start`.** Don't let the game auto-start on
  page load. The cleanest place to do this is wherever the game's own
  "start a new game" function lives — wrap it so it only runs in response to
  `window.addEventListener("alphago:start", ...)`, and show a simple
  "waiting for the game to start…" overlay (absolutely positioned, `inset:0`,
  theme-colored background, toggled by a `.hidden` class) until then.
- **One `gameOverReported` flag per run**, set the instant the score-ending
  condition is true, checked before every `AlphaGo.gameOver()` call. Cheaper
  and more reliable than trying to reason about "did we already send this"
  from UI state.
- **Restart = go back to waiting, not an immediate new board.** Any
  "play again"/"retry" UI action in the game should re-show the waiting
  overlay and ignore input until the next `start`, rather than starting a
  fresh scored run on its own. The host (or the test host, in dev) decides
  when the next run begins.
- **Neutralize persistence by swapping the backing store, not by deleting
  code.** If a game already has a storage abstraction (a `StorageManager`
  class, a `saveState()`/`loadState()` pair), redirect it to an in-memory
  object instead of real `localStorage`/`sessionStorage`. Keeps the rest of
  the game's code untouched and still diffable against upstream.
- **`t(key)` should re-read `AlphaGo.lang` on every call**, not cache it at
  script-load time — `lang` isn't known until the `start` message arrives,
  which is after scripts have already run.
- **Drop legacy asset formats aggressively.** `.eot`/`.svg` webfonts, old
  build tooling (Sass sources, Rakefiles, lint configs), iOS splash-screen
  images — none of it is needed inside a modern WebView iframe. 2048 went
  from several hundred KB of vendor cruft down to 136 KB just from this.

## Things to double check per game, not just assume from 2048

- **Does the game have its own animation/game loop (`requestAnimationFrame`
  ticking every frame), not just event-driven moves?** 2048 only recomputes
  on a keypress/swipe, so `pause` only needed to gate input. Arcade games
  (Snake, Hextris) will have a running loop that must actually be stopped on
  `alphago:pause` and restarted cleanly on `resume`, or they'll keep
  burning battery/CPU in the background.
- **Multiple "ends" to a run.** 2048 has two: an unambiguous loss, and an
  ambiguous win (player can keep going). Games with their own win/continue
  branching need the same explicit "decline = end of run" mapping — don't
  assume there's only one exit path.
- **Font/asset licenses are often undocumented in the source repo itself**
  (Clear Sans here). Treat "MIT" in the repo's `LICENSE.txt` as covering the
  *code* only; chase down asset licenses separately and mark them
  "pending verification" in `CREDITS.md` rather than asserting them as fact.
- **Best-score / high-score UI tied to local storage should probably be
  removed outright**, not just disconnected from real storage — a number
  that silently resets every reload is confusing next to a real
  server-tracked leaderboard shown elsewhere in the host app.

## Still unverified for 2048 (needs a real device/browser, not available in this environment)

- Actual swipe-without-page-scroll behavior inside a real sandboxed iframe.
- Light/dark Telegram theme switching mid-play.
- Load time on throttled slow 3G and real low-end Android performance.
- `max_score_per_second` is a placeholder (1000) — needs tuning from a real
  best-run.
