# Game Licenses Index

One row per game in `games/`. Source of truth for license status; details live in each game's own `games/<slug>/game.json` and `games/<slug>/CREDITS.md`.

| Slug | Code license | Asset license | Status |
|---|---|---|---|
| 2048 | MIT (Gabriele Cirulli) | Apache-2.0 claimed for Clear Sans font — **pending verification** | pending |
| minesweeper | MIT (Tejas Wavde) | none | pending |
| memory | MIT (Tejas Wavde) | none (emoji glyphs only) | pending |
| lights-out | MIT (Tejas Wavde) | none | pending |
| mini-sudoku | MIT (Tejas Wavde) | none | pending |
| connect-four | MIT (Tejas Wavde) | none | pending |
| 0hh1 | MIT (Martin Kool / Q42, via florisluiten/0hh1 mirror — **provenance one step removed, verify**) | OFL claimed for bundled fonts — **pending verification** | pending |
| snake | MIT (AlphaGo project — original, not imported) | none | pending |
| wordle | MIT (AlphaGo project — original game code) | SCOWL permissive license (word list), see games/wordle/WORDLIST-LICENSE.txt | pending |
| breakout | MIT (AlphaGo project — original, not imported) | none | pending |
| dummy | n/a (internal fixture, not shipped) | n/a | not shipped |

**Hextris was not shipped.** It was the plan's 10th catalog slot (GPLv3); Breakout above is the plan's own named fallback, used instead of standing up GPL-compliance infrastructure (public fork repo, license distribution) for one game. See `games/breakout/CREDITS.md` for the full reasoning — swapping in real Hextris later is still possible if that infrastructure gets built.

See `01-game-adaptation-plan.md` section 11 for the GPL/Hextris handling rules and the per-game checklist.
