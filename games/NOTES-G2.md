# Phase G2 notes (wavde/games batch) — for G3

Adapted Minesweeper, Memory Match, Lights Out, Mini Sudoku, Connect Four from
[wavde/games](https://github.com/wavde/games), all MIT. Lessons for G3 (0hh1,
Snake, Wordle-style, Hextris).

## Patterns that worked, reuse as-is

- **Patch a shared storage helper once, not per-game.** Four of these five
  games used one shared `gamekit.js` with a `Gamekit.storage(prefix)`
  factory. Instead of touching each game's score/persistence code, I patched
  `storage()` itself to back onto an in-memory object instead of real
  `localStorage`, then copied the patched file into each game folder. One
  edit, five games covered. Look for this kind of shared helper before
  doing per-game surgery.
- **Split "abandon the run" from "reset my progress on this run."** Not
  every "reset"-labeled button should go through the full
  wait-for-host-start cycle. A button that clears moves/entries on the
  *same* puzzle (Lights Out's "reset", Mini Sudoku's "reset", Connect Four's
  "undo") is an in-run action — gate it on `waitingForStart`/`paused` but
  don't send it through the restart contract. Only buttons that change the
  puzzle/board itself ("new", difficulty change, mode change) should abandon
  the run and wait for the next `start`.
- **Seed policy for generator-based puzzles**: always prefer the host's
  `start.seed` when present, fall back to a random seed (never
  `Date`-based) for the idle board shown pre-`start`. Applies to any game
  with a seedable PRNG-driven generator, not just the two games the plan
  calls out by name as "daily puzzles."
- **Dead code can still be a persistence leak waiting to happen.** The
  shared `manpage.js` had an `autoOpen(id)` function that used real
  `localStorage` to remember "already shown this game's help once" —
  unreachable in these builds since no `index.html` calls it anymore, but
  still shipped. Removed it (and the now-unused `cssEscape` helper) from the
  shared file rather than leaving working-but-dead `localStorage` calls in
  the bundle. Worth a repo-wide `grep -rn localStorage` as a final check on
  any batch, not just a per-game spot-check.
- **Blocking dialogs (`confirm()`/`alert()`/`prompt()`) are a real bug, not
  a nice-to-have fix.** The production sandbox
  (`sandbox="allow-scripts allow-same-origin"`, no `allow-modals`) silently
  breaks these. Found one in Mini Sudoku's "reset" button — would have
  silently stopped working in production. Grep every game for
  `confirm(`/`alert(`/`prompt(` before considering it done.
- **Cut features that don't fit the single-player session model**, don't
  just leave them half-working. Connect Four's local 2-player mode was
  removed outright (not hidden, not left as dead code) since one `gameover`
  per run, mapped to one player, doesn't have a clean answer for a
  pass-and-play match.
- **AI already exists? Don't rebuild it.** Connect Four already had a
  working alpha-beta AI at three depths — the plan flagged "verify an AI
  opponent exists" as a risk, and it did. Always check before assuming you
  need to write one.

## Judgment calls flagged as placeholders (need real playtest data)

- Lights Out's "par" = scramble count, not a true computed minimum solve
  length (would need to solve the puzzle's linear system over GF(2)).
- Mini Sudoku's mistake-tracking is new (upstream had none) and simple
  (conflict-on-placement → +1); there's no hint feature at all, so the
  formula's hint term is permanently 0 until one is built.
- Every `diff_mult`/multiplier the plan's scoring table mentioned without
  giving exact numbers (Connect Four, Mini Sudoku) got a reasonable-looking
  placeholder (documented per-game in each `CREDITS.md`) — these all need
  tuning once real playtest data exists, same as `max_score_per_second`
  everywhere.

## Still unverified (needs a real device/browser, not available in this environment)

- All the same gaps as 2048: swipe/touch behavior, live theme switching,
  load time on throttled 3G, real low-end Android performance.
- Minesweeper's long-press-to-flag timing (400ms) and whether it fights the
  system context menu inside a real WebView — upstream already calls
  `e.preventDefault()` on `contextmenu`, should be fine, but untested here.
