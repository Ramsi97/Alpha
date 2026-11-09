# Credits

- **Source:** [wavde/games](https://github.com/wavde/games) (`memory/`)
- **Author:** Tejas Wavde
- **License:** MIT (see `LICENSE`, unchanged)

## What was changed from upstream

- **Bridge integration** (`game.js`): gated on `alphago:start`; "New game"
  and the size dropdown now abandon the current run and wait for the next
  `start` rather than dealing a fresh board immediately. `gameOver` fires
  once, in `finish()`, with `score = size_mult * max(0, 1000 - 10*moves -
  2*seconds)` per plan section 7 (`size_mult` 1/2/3 for 4×4/6×6/8×8).
- **Persistence neutralized** (`gamekit.js`, shared with the other
  wavde-sourced games in this batch): `Gamekit.storage()` now always backs
  onto an in-memory object, never real `localStorage`. The "Best" box still
  shows during play but only reflects this page-load's session, not a real
  persisted record — true best-of-all-time lives server-side.
- **Pause/resume**: the timer interval checks a `paused` flag and
  `startTime` is shifted forward by the paused duration on resume.
- **Removed**: Google Fonts remote stylesheet + preconnects, `manifest.json`
  / apple-touch-icon links, the hub back-link, and the automatic man-page
  popup on load (kept the on-demand "? man" button).
- **Added**: `../_shared/theme.css` and the waiting-for-host overlay.

## Known simplifications / needs verification

- `max_score_per_second` (60) is a starting placeholder, not yet tuned from
  a real playtest.
- Man-page help text is English-only, not wired into i18n yet.
