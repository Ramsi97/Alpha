# Credits

- **Source:** original implementation for this project, not imported from
  any third-party repo. Plan section 8 flagged the available upstream Snake
  candidates as beginner-quality and suggested writing a small one instead
  ("about 100 lines of canvas... grid-based movement, swipe controls, speed
  increases every N foods") — that's exactly what this is.
- **Author:** AlphaGo project
- **License:** MIT (see `LICENSE`)

## Design notes

- 20×20 grid, canvas-rendered, responsive to the board's actual pixel size
  (accounts for device pixel ratio).
- Speed increases every 5 food eaten (`SPEEDUP_EVERY`), down to a floor of
  70ms per tick from a starting 160ms.
- Standard snake collision rule implemented carefully: when the move eats
  food, the tail does *not* vacate this tick, so the full body (including
  the current tail cell) is checked for self-collision; otherwise the tail
  cell is excluded from the check since it's about to move away.
- Direction input can't reverse straight into the snake's own neck
  (ignored, not queued).
- The game loop runs continuously via a self-rescheduling `setTimeout` for
  its entire lifetime (started once at load) — `waitingForStart`/`paused`
  just gate whether a tick does anything, rather than the loop being
  started/stopped/recreated across runs. Simpler and avoids any
  start/stop timer bugs across repeated runs.
- Score: `food * 10` per plan section 7. `gameOver` fires once, on wall or
  self collision.

## Known gaps / needs verification

- No real device/browser testing was possible in this environment —
  swipe-threshold feel (15px) and tick timing on a real low-end Android
  phone are unverified.
- `max_score_per_second` (40) is a starting placeholder.
