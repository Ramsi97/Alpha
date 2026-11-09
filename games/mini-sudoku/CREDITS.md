# Credits

- **Source:** [wavde/games](https://github.com/wavde/games) (`mini-sudoku/`)
- **Author:** Tejas Wavde
- **License:** MIT (see `LICENSE`, unchanged)

## What was changed from upstream

- **Bridge integration** (`game.js`): "new" and difficulty-chip changes end
  the run and wait for the host's next `start`; "undo"/"reset" stay in-run.
  `gameOver` fires once, on solve, with `score = diff_mult * max(100, 1000 -
  2*seconds - 50*mistakes - 100*hints)` per plan section 7 (`diff_mult`
  1/1.5/2 for easy/medium/hard — not specified exactly by the plan, chosen
  as a starting placeholder).
- **Mistake tracking added**: upstream had no mistake counter at all (only a
  transient "fix conflicts" status message). Added a simple counter —
  placing a non-pencil digit that creates a new conflict increments
  `mistakes` by one. **Hints are always 0**: there's no hint feature in this
  build, so that term of the formula is currently inert. Worth adding a real
  hint button later if the formula should actually use it.
- **Seed source**: upstream defaulted to `Gamekit.dailySeed()` (client-date
  hash) — replaced with the host's `start.seed`, falling back to a random
  seed only for the idle board shown pre-`start`.
- **Removed the blocking `confirm()`** on "reset": the production sandbox
  (`sandbox="allow-scripts allow-same-origin"`, plan section 9.2) has no
  `allow-modals`, so `window.confirm()` would be suppressed or throw —
  "reset" would have silently stopped working. Clearing entries isn't
  destructive enough to need a confirmation anyway (no real persistence is
  at stake).
- **Persistence neutralized** (shared `gamekit.js`): in-memory only.
- **Removed**: Google Fonts + preconnects, hub links, PWA manifest/icon
  links, automatic man-page popup (kept the "? man" button).
- **Added**: `../_shared/theme.css` and the waiting-for-host overlay.

## Known simplifications / needs verification

- `diff_mult` values (1/1.5/2) and `max_score_per_second` (50) are starting
  placeholders, not yet tuned from a real playtest.
- Consider a real hint feature later if the hints term of the score formula
  should do anything.
