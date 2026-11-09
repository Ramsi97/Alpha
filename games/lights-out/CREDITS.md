# Credits

- **Source:** [wavde/games](https://github.com/wavde/games) (`lights-out/`)
- **Author:** Tejas Wavde
- **License:** MIT (see `LICENSE`, unchanged)

## What was changed from upstream

- **Bridge integration** (`game.js`): "new" and difficulty-chip changes end
  the run and wait for the host's next `start`; "undo" and "reset" stay
  in-run (they don't change the puzzle, just the player's progress on it).
  `gameOver` fires once, on solve, with `score = max(0, 1000 - 25*max(0,
  moves - par))` per plan section 7.
- **Seed source**: upstream defaulted new puzzles to `Gamekit.dailySeed()`
  (a hash of the player's local date) — replaced with the seed from the
  host's `start` message, falling back to a random seed only for the idle
  board shown before the first `start` (never the device clock, per plan
  section 7 notes).
- **Persistence neutralized** (shared `gamekit.js`, same patch as the other
  wavde-sourced games in this batch): `Gamekit.storage()` is in-memory only.
- **Removed**: Google Fonts remote stylesheet + preconnects, hub links, PWA
  manifest/icon links, automatic man-page popup (kept the "? man" button).
- **Added**: `../_shared/theme.css` and the waiting-for-host overlay.

## Known simplification — "par" is approximate

"Par" is set to the scramble count used to generate the puzzle (`DIFFS[diff]`
= 3/6/10 presses), **not** a computed true minimum solve length. Because
pressing the same cell twice cancels out, the actual shortest solution can
occasionally be shorter than the scramble count. Computing the true minimum
requires solving the puzzle's underlying linear system over GF(2) — out of
scope for this pass. This means a small number of players could occasionally
score slightly lower than they "deserve" relative to the true optimum. Flagged
in the plan itself as a risk for this game ("check generator for fairness") —
worth revisiting if score complaints come in.

`max_score_per_second` (150) is a starting placeholder, not yet tuned.
