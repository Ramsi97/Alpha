# Credits

- **Source:** the original [Q42/0hh1](https://github.com/Q42/0hh1) repo
  named in the plan **no longer exists on GitHub** (404 as of this adaptation).
  Pulled instead from [florisluiten/0hh1](https://github.com/florisluiten/0hh1),
  a faithful mirror — its `LICENSE` file carries the same MIT text and 2014
  Q42 copyright notice as the original, and its code/credits match Q42's
  known game (same author name "Martin Kool" in the About screen, same
  file structure). Not independently verified against the original repo's
  git history since that history is gone; **worth a second check before
  shipping** given the provenance is one step removed from the primary
  source.
- **Author:** Martin Kool / Q42 (2014)
- **Code license:** MIT (see `LICENSE`, unchanged)
- **Asset license:** bundled fonts `JosefinSans-Bold.ttf` and
  `Molle-Regular.ttf` — no separate license file ships with them in this
  repo. Josefin Sans is a well-known Google/SIL Open Font License font;
  Molle is also an OFL Google Font. Both **should** be OFL, consistent with
  the game's own MIT code license, but this is carried over unverified —
  confirm before shipping (same category of gap as 2048's Clear Sans font).

## What was changed from upstream

- **Bridge integration** (`js/game.js`): a puzzle only begins once the host
  sends `start` (gated at the size-tile tap handler and the tile-tap
  handler); the `alphago:start`/`pause`/`resume` listeners are registered
  immediately at module load, **not** inside upstream's `addEventListeners()`
  — that function is only called ~4.2 seconds after load (after the
  title-screen reveal animation), which would have missed a `start` sent
  right after `ready`.
- **Each completed puzzle is one scored run.** Plan section 8 explicitly
  leaves this as an open choice ("report each completed puzzle as a run, or
  a streak of puzzles as one run — decide in playtesting"). Picked
  one-puzzle-per-run for consistency with every other game in this catalog:
  after `endGame()`, the size-chooser reappears behind the waiting overlay
  and picking a new size requires a fresh `start`. `gameOver` fires once per
  puzzle with `score = size² * 10 + max(0, 300 - seconds)` (plan section 7).
  Quitting mid-puzzle (`quitCurrentGame`, the "back" action) reports nothing.
- **Dropped the legacy lifetime-points system**: upstream tracked a
  cumulative "trophy score" across every puzzle ever solved, in real
  `localStorage` (`getScore`/`setScore`), shown next to a trophy icon and
  used to build a tweet-your-score link. Removed the trophy UI and the
  Twitter share button/link entirely (`index.html`, checklist 6.2 — social
  buttons), and reduced `getScore()` to a no-op-returning stub (`setScore`,
  `animateScore`, `updateTweetUrl` were deleted outright as fully dead
  code). A handful of now-harmless jQuery calls targeting the removed
  `#score`/`#scorenr`/`#tweeturl` elements were left in place rather than
  hunted down one by one — jQuery no-ops silently on an empty selection, so
  these do nothing instead of erroring.
- **Tutorial "seen before" flag and the dead trophy counter** both moved
  from real `localStorage` to in-memory variables (plan section 6.3). One
  behavior change worth knowing about: upstream only scored a player's
  *first-ever* tutorial playthrough (via a persisted flag); with in-memory
  storage this becomes "first tutorial playthrough per app session"
  instead. Low-stakes (tutorial puzzles are tiny), not worth more
  engineering to preserve exactly.
- **Fixed a latent crash**: `backButtonPressed()` called
  `navigator.app.exitApp()` unconditionally on the title screen.
  `navigator.app` is a Cordova-only API that doesn't exist in a plain
  WebView — pressing Escape on the title screen would have thrown. Now
  guarded with `if (navigator.app)`.
- **Removed**: the two apple-touch/favicon icon links (not meaningful
  inside an iframe) and their backing image files, plus the now-unused
  trophy/twitter icon images.
- **Added**: `../_shared/theme.css` and a full-screen waiting-for-host
  overlay (kept the game's own near-black `#222` background — it's the
  game's deliberate dark aesthetic, not an accidental hardcoded
  black/white screen, same judgment call as 2048's cream background).
- **Not changed**: puzzle generation still uses plain `Math.random()`
  (no seed from the host). The plan doesn't call out 0hh1 as a "daily
  puzzle" game the way it does Mini Sudoku/Wordle-style, so there's no
  server-seed requirement here to begin with.

## Known deviation from the plan's table

The plan's scoring table lists variants as `4x4/6x6/8x8` with `max_score:
1000`. Upstream actually offers four sizes (4/6/8/10), and dropping the
10×10 option would have meant reshaping a fixed 2×2 HTML grid of size
tiles for a fairly marginal gain. Kept all four sizes; adjusted
`max_score` to 1300 (10² × 10 + 300) and `variants` to include `"10x10"`
to match. `max_score_per_second` (120) is a starting placeholder either way.
