# Credits

- **Source:** [wavde/games](https://github.com/wavde/games) (`minesweeper/`)
- **Author:** Tejas Wavde
- **License:** MIT (see `LICENSE`, unchanged)

## What was changed from upstream

- **Bridge integration** (`game.js`): gated on `alphago:start`; "New game" and
  the difficulty dropdown now abandon the current run and wait for the next
  `start` instead of dealing a new board immediately. Reports only on a win
  (score via `base * max(0.2, 1 - seconds/target)` per difficulty, matching
  plan section 7); a loss still sends `gameover` with score 0 so the host can
  close the session.
- **Pause/resume**: the elapsed-time interval now checks a `paused` flag, and
  `timerStart` is shifted forward by the paused duration on resume so time
  spent backgrounded isn't counted against the score.
- **No persistence to remove**: this game never used `localStorage` upstream
  (no best-time tracking), so nothing needed neutralizing.
- **Removed**: Google Fonts remote stylesheet + preconnects (checklist 6.2 —
  falls back to the existing local monospace stack in `shared.css`), the
  `manifest.json`/apple-touch-icon links (not meaningful inside an iframe),
  the "← all games" hub link, and the automatic man-page popup on load (kept
  the on-demand "? man" button — auto-popping a modal over the waiting
  overlay on every load was poor fit for an embedded game).
- **Added**: `../_shared/theme.css` and a "waiting for the game to start…"
  overlay (`.alphago-waiting`).

## Known simplifications / needs verification

- `max_score_per_second` (50) and the win-score constants are the plan's
  starting values, not yet tuned from a real playtest.
- The help overlay (`manpage.js`/`.css`, the "? man" button) is English-only
  and not wired into `STRINGS`/i18n — low-risk to leave as-is for now since
  it's optional reference text, not core gameplay, but flag before shipping
  translated builds.
