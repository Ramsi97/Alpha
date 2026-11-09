# Credits

- **Game code source:** original implementation for this project, not
  imported from any third-party repo. Plan section 8 explicitly calls for
  a vanilla-JS rewrite rather than importing an existing wordle-clone repo
  ("no in-browser Babel, no React CDN... check the word list's license
  separately from the game code").
- **Game code author:** AlphaGo project
- **Game code license:** MIT (see `LICENSE`)
- **Word list source:** SCOWL (Spell Checker Oriented Word Lists), via
  Debian's `wamerican` package, which bundles a derivative of SCOWL plus
  the public-domain Moby Words II list. Permissively licensed — full
  permission notice reproduced in `WORDLIST-LICENSE.txt` as required by its
  terms.
- **Word list license:** see `WORDLIST-LICENSE.txt` (separate from the MIT
  code license, per plan section 8's explicit instruction to check it
  independently)

## How the word lists were built

- `WORDLE_GUESSES` (4,667 words): every 5-letter, all-lowercase entry from
  `/usr/share/dict/american-english` (SCOWL-derived). This is the
  acceptance list — any of these can be typed and submitted as a guess,
  same as real Wordle accepting any valid dictionary word.
- `WORDLE_ANSWERS` (559 words): a hand-curated subset of `WORDLE_GUESSES`,
  picked for everyday recognizability as a *daily answer* specifically
  (the full dictionary subset includes plenty of valid-but-obscure words
  like "abaft" or "abets" that would make a frustrating daily puzzle).
  This curation is original selection work by this project, not copied
  from any other Wordle-style word list — deliberately avoids the common
  "extracted from the original NYT Wordle's client source" word lists that
  circulate online, whose own licensing is murkier.

## Daily word delivery (plan section 8)

The day's answer index comes from the host's `start.seed` field
(`idx = seed mod WORDLE_ANSWERS.length`) — never the player's device clock.
This is the plan's own "simplest safe path": the word list ships inside the
client, so a determined player could inspect it and the index together and
work out the answer early. The plan accepts this tradeoff explicitly and
expects the **backend** to cap the real defense: one reward per day,
enforced server-side, regardless of how many times the client is reloaded
or the puzzle is "replayed." There is deliberately no in-client "play
again" button — once a run ends (win or loss), the result is final for
that `start.seed`.

If the host sends no seed at all (e.g. the local test host without one
configured), the client picks a random answer instead and treats the
round as practice — not a real daily puzzle. Fine for local testing, but
the backend should never omit a seed in production.

## Scoring

`gameOver` fires exactly once: `(7 - guesses) * 150` on a win (so 1 guess =
900, 6 guesses = 150), `0` on using all 6 guesses without the word. Per
plan section 7. `max_score_per_second` (90) is a starting placeholder, not
tuned from real play data.

## Known gaps

- Letter-feedback duplicate-letter handling (the trickiest part of any
  Wordle clone) was unit-tested against several hand-checked cases
  (`allot` vs `apple`, `radar` vs `abide`, `cilia` vs `lilac`, etc.) and
  confirmed correct, but the actual on-screen UI/keyboard interaction is
  unverified without a real browser in this environment.
- No real device/browser testing (same gap as every other game this pass).
