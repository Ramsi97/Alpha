# Credits

- **Source:** [gabrielecirulli/2048](https://github.com/gabrielecirulli/2048)
- **Author:** Gabriele Cirulli
- **Code license:** MIT (see `LICENSE`, unchanged)
- **Asset license:** the "Clear Sans" webfont (`style/fonts/`) is Intel's
  Clear Sans, publicly released under the Apache License 2.0. The upstream
  repo does not ship a font-specific license file, so this is carried over
  from the public record rather than verified in-repo — **confirm before
  shipping** (plan `01-game-adaptation-plan.md` section 3/11).

## What was changed from upstream

- **Bridge integration** (`js/game_manager.js`): a run now only starts on the
  host's `start` message; input is ignored until then. `AlphaGo.gameOver()`
  fires exactly once per run — immediately on a loss, or when the player
  declines to continue after reaching 2048 (clicking "Try again" on the win
  screen instead of "Keep going"). Any restart puts the board back into a
  "waiting for start" state instead of beginning a new run locally — the host
  decides when the next run begins.
- **Persistence removed** (`js/local_storage_manager.js`): always uses the
  in-memory `fakeStorage` now, never real `localStorage`. Nothing survives a
  page reload — no best-score, no resumed game state. The server is the only
  source of truth for scores/leaderboards.
- **Best-score UI removed** (`js/html_actuator.js`, `index.html`): the "BEST"
  box was dropped along with its storage, since a value that resets on every
  reload would be misleading next to the server-tracked leaderboard shown
  elsewhere in the Mini App.
- **Strings externalized** (`strings.js`): all visible text moved into one
  `STRINGS.en` object, applied via `data-i18n` attributes. Afaan Oromo/Amharic
  can be added later by filling the same keys. Two inline `<strong>` emphases
  from the original copy ("2048 tile!", "merge into one!") were flattened to
  plain text to keep the translation keys simple — purely cosmetic.
- **Mobile/theme wiring** (`index.html`): added `../_shared/theme.css`,
  `viewport-fit=cover`, and a "waiting for host" overlay. The game's own
  cream/tan color scheme was kept as-is (it's the game's visual identity, not
  an accidental hardcoded white/black background) — only the new overlay and
  the outer `html`/`body` inherit the Telegram theme variables.
- **Footer rewritten**: removed the upstream donation/"official site" notice;
  replaced with a one-line attribution linking back to the source repo and
  this file.
- **Trimmed for size** (136 KB total, well under the 1–2 MB budget):
  dropped `.eot`/`.svg` legacy webfont formats (kept `.woff` only — every
  Telegram client target is a modern Chromium/WebKit WebView), dropped the
  iOS splash-screen images in `meta/`, dropped the Sass source and
  `Rakefile`/`.jshintrc` build tooling (not needed without a build step).

## Still needs real verification (can't be done without a device/browser)

- Confirm Clear Sans' Apache-2.0 status against Intel's actual release terms.
- Playtest to set real `max_score_per_second` (currently a placeholder:
  1000/sec, i.e. an average over a session — tune from actual best-run data
  per plan section 7).
- Run the full QA matrix (section 9.3) on a real low-end Android phone inside
  Telegram: light/dark theme, swipe-without-scroll, pause/resume on
  backgrounding, load time on throttled 3G.
