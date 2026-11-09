# Credits

- **Source:** [wavde/games](https://github.com/wavde/games) (`connect-four/`)
- **Author:** Tejas Wavde
- **License:** MIT (see `LICENSE`, unchanged). Alpha-beta AI with a
  center-weighted evaluation function already existed upstream at three
  depths (2/4/6) — plan section 8 asked to verify an AI exists; it does, no
  AI work was needed.

## What was changed from upstream

- **Dropped local 2-player mode**: upstream had a "2 players local"
  pass-and-play option. Removed it — this architecture scores single-player
  sessions against the host/backend (one `gameover` → one XP award per
  player), and a two-human-on-one-device match doesn't fit that model
  cleanly. The mode selector now only offers the two AI-opponent options.
- **Bridge integration** (`game.js`): "new game", mode change, and
  difficulty change all end the run and wait for the host's next `start`;
  "undo" stays in-run. `gameOver` fires once, when a win/draw/loss is
  detected, with `score = round(raw * diff_mult)` where `raw` is 500 +
  (42-moves)*10 for a win, 100 for a draw, 0 for a loss (plan section 7);
  `diff_mult` (0.7/1/1.4 for easy/medium/hard) isn't specified exactly by the
  plan — chosen as a starting placeholder.
- **Pause/resume**: pausing cancels any pending AI "thinking" timeout
  (harmless either way since it's only 150ms) and blocks new human moves;
  resuming re-triggers the AI's move if it was its turn.
- **Persistence neutralized** (shared `gamekit.js`): in-memory only (stored
  mode/difficulty preference, not scores — no score persistence existed
  upstream for this game).
- **Removed**: Google Fonts + preconnects, hub links, PWA manifest/icon
  links, automatic man-page popup (kept the "? man" button).
- **Added**: `../_shared/theme.css` and the waiting-for-host overlay.

## Known simplifications / needs verification

- `diff_mult` values and `max_score_per_second` (80) are starting
  placeholders, not yet tuned from a real playtest.
