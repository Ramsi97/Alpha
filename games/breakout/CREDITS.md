# Credits

- **Source:** original implementation for this project, not imported from
  any third-party repo.
- **Author:** AlphaGo project
- **License:** MIT (see `LICENSE`)

## Why Breakout instead of Hextris

The plan's 10th catalog slot was Hextris (GPLv3), with Breakout named as
the explicit fallback "if Hextris is dropped" (plan section 3/section 8/
section 11). Picked the fallback here rather than importing Hextris,
because:

- GPLv3 compliance for a game served inside an iframe needs real
  infrastructure this project doesn't have yet: a public repo for the
  *modified* source, a license-text distribution point, and (per the
  plan's own section 11) ideally legal sign-off on whether the host app
  counts as a "combined work" with an embedded GPL iframe. None of that
  exists yet, and standing it up properly is a bigger undertaking than
  adapting one game.
- The plan itself frames this as an acceptable, anticipated substitution,
  not a last resort — it's listed as the named fallback, not something
  improvised here.

The couple of small Breakout repos found on GitHub while scoping this had
either no license file or licenses that weren't worth the verification
overhead for a ~150-line game. Writing an original implementation (same
approach as Snake) sidesteps that entirely.

**If GPL compliance infrastructure gets built later**, swapping this for
the real Hextris is still on the table — nothing here forecloses that;
it's simply not blocking the rest of the catalog on it now.

## Design notes

- Fixed logical coordinate space (300×400 units) scaled to the actual
  canvas size via `ctx.scale()`, so collision math doesn't need to care
  about device pixel ratio or responsive sizing.
- 5 rows × 8 columns of bricks, top row worth 50 points down to 10 for the
  bottom row (classic tiered Breakout scoring).
- Paddle follows touch/mouse x directly (not relative drag) for responsive
  one-handed play; arrow keys/WASD as an alternative for desktop testing.
- Ball-paddle bounce angle responds to where on the paddle it was hit
  (offset from center scaled to a max horizontal velocity), not a fixed
  reflection — gives the player some control over aim.
- 3 lives; losing the ball re-serves it rather than ending the run
  immediately. `gameOver` fires once, on either clearing every brick (win,
  with a `lives * 100` bonus added) or losing the last life (loss).
- Frame delta-time is clamped to 50ms to absorb the large gap that can
  occur after the WebView is backgrounded, on top of explicitly resetting
  the clock reference on `alphago:resume`.
- No in-game "new game" button — consistent with how every arcade game in
  this catalog works, the host decides when the next run begins (plan
  section 6.6); after a run ends the waiting overlay reappears and nothing
  happens until the next `start`.

## Known gaps

- No real device/browser testing was possible in this environment —
  touch-drag paddle feel and collision robustness at speed are unverified.
- `max_score_per_second` (100) is a starting placeholder.
