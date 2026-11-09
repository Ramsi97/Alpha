# games/

Self-hosted HTML5 games adapted for the AlphaGo Telegram Mini App. Full spec: `../01-game-adaptation-plan.md`.

## Layout

- `_shared/` — files every game includes directly:
  - `alphago-bridge.js` — the `postMessage` contract (`AlphaGo.ready/score/gameOver/error`, `alphago:*` events). Also mirrors host theme params onto `--tg-theme-*` CSS variables.
  - `theme.css` — Telegram theme variables + mobile base styles (no page scroll/zoom, 44px tap targets, safe-area padding).
  - `i18n-helper.js` — `AlphaGoI18n(STRINGS, lang)` → `t(key)` lookup with English fallback.
- `_tools/`
  - `game-manifest.schema.json` — schema for each game's `game.json`.
  - `validate-manifest.mjs` — run with `node games/_tools/validate-manifest.mjs`; checks every `games/<slug>/game.json` against the schema plus semantic checks (slug matches folder, `entry`/`thumbnail` exist, `LICENSE`/`CREDITS.md` present).
  - `test-host.html` — local QA harness. Serve `games/` with any static server and open `_tools/test-host.html`, e.g.:
    ```
    cd games && python3 -m http.server 8731
    # open http://localhost:8731/_tools/test-host.html
    ```
    Add new slugs to the `GAME_SLUGS` array at the top of its script when you add a game folder.
- `<slug>/` — one folder per game: `index.html`, `game.js`/assets, `game.json`, `LICENSE` (original, unchanged), `CREDITS.md`.
- `dummy/` — minimal fixture game (not shipped) that exercises the full contract; used to prove the tooling above works before any real game is imported. Safe to use as a template for `index.html`'s `<head>` wiring (viewport meta, theme.css, bridge script order).

## Adding a game

Follow the checklist in `01-game-adaptation-plan.md` section 6, then:
1. Add the slug to `_tools/test-host.html`'s `GAME_SLUGS` array.
2. Run `node games/_tools/validate-manifest.mjs` — must pass before QA.
3. Add a row to `../LICENSES.md`.
