# Phase G3 notes (0hh1, Snake, Wordle-style, Breakout)

## Key decisions made without stopping to ask (per user instruction to push
through the whole backlog and fix things together afterward)

- **Q42/0hh1's original repo is gone from GitHub** (404). Used
  [florisluiten/0hh1](https://github.com/florisluiten/0hh1), a mirror whose
  `LICENSE` carries the same MIT/Q42 2014 copyright — but this provenance
  is one step removed from the primary source and flagged as worth a
  second check in `games/0hh1/CREDITS.md`.
- **0hh1 kept all four upstream board sizes** (4/6/8/10), not just the
  4x4/6x6/8x8 the plan's table lists — reshaping a fixed 2×2 HTML grid of
  size-choice tiles for one fewer option wasn't worth it. `max_score`
  adjusted from 1000 to 1300 to match. Documented in `games/0hh1/CREDITS.md`.
- **0hh1: each completed puzzle is one scored run**, not a streak of
  puzzles — plan section 8 explicitly left this open; picked for
  consistency with every other game in the catalog.
- **Snake and Breakout were written from scratch**, not imported — the
  plan's own text suggested this for Snake ("if the found code is weak,
  write your own"); for Breakout the small third-party repos found had
  weak/missing license files, not worth the verification overhead for
  ~150 lines of game.
- **Wordle-style's word list was hand-curated from the system's SCOWL
  dictionary** (`/usr/share/dict/american-english`, permissively
  licensed, full attribution in `games/wordle/WORDLIST-LICENSE.txt`) —
  4,667 words as the broad guess-acceptance list, 559 hand-picked common
  words as the actual daily-answer pool. Deliberately did **not** use any
  of the word lists that circulate online extracted from the real NYT
  Wordle's client source — their own licensing is murkier than just using
  a properly-attributed dictionary.
- **Hextris was dropped in favor of Breakout**, the plan's own named
  fallback — GPLv3 compliance needs infrastructure (public fork repo,
  license distribution point) this project doesn't have yet. Full
  reasoning in `games/breakout/CREDITS.md`. This is reversible — nothing
  forecloses swapping real Hextris in later.

## Patterns that worked, reuse going forward

- **For "write it yourself" games (Snake, Breakout), keep the game loop
  infrastructure running for the entire page lifetime**, started once at
  load, and gate actual gameplay purely on `waitingForStart`/`paused`
  booleans checked inside the loop — rather than starting/stopping/
  recreating timers or rAF callbacks across runs. Simpler, and there's no
  "did I clear the right timer" class of bug to worry about.
- **For bridge listeners that must never be missed, register them at
  module load, not inside whatever function the vendor code calls last.**
  0hh1's `addEventListeners()` only ran ~4.2 seconds after page load
  (after a title-screen animation) — had the `alphago:start` listener
  lived there, a `start` sent right after `ready` would have been lost.
  Always check when a vendor init function actually runs before relying
  on it as the home for bridge wiring.
- **A legacy "lifetime score" system (separate from the real per-run
  score) is a common pattern in these older single-page games** (0hh1 had
  one backed by real `localStorage`). Cleanest fix: patch the storage
  functions themselves to in-memory, and if the whole feature's UI is
  being removed anyway, deleting the DOM elements is enough — jQuery (and
  vanilla `querySelector`-based code written defensively) silently no-ops
  on missing elements, so you don't have to hunt down and edit every call
  site that referenced them.
- **Always check what a vendor init function does in a plain browser when
  it was written for a hybrid app shell (Cordova/PhoneGap).** Found a real
  crash (`navigator.app.exitApp()` with no guard) in 0hh1 this way — worth
  a quick grep for `navigator.app`, `cordova`, `PhoneGap` in any older
  "mobile web game" codebase.
- **Unit-test tricky pure logic directly in Node before trusting it**,
  especially anything with classic off-by-one traps (Wordle's
  duplicate-letter scoring). Caught nothing wrong this time, but it took
  four lines of `node -e` to get real confidence instead of just "the code
  looks right."

## Still unverified for all of G3 (needs a real device/browser)

- Same gaps as every prior phase: swipe/touch feel, live theme switching,
  load time on throttled 3G, real low-end Android performance.
- Breakout's touch-drag paddle responsiveness and collision robustness at
  speed specifically — never watched it actually run.
- 0hh1's font license (Josefin Sans / Molle — likely OFL, unverified) and
  its own provenance-one-step-removed source repo.
