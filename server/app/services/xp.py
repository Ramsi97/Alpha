"""XP, levels, and the per-run award formula (plan sections 8.4, 9.1).

The run-threshold/multiplier table and the daily game XP cap are meant to
live in the `settings` table (plan section 2 principle 4: tunables in the
DB, not code). This module takes them as parameters with the plan's own
defaults, rather than reading `settings` itself — callers (the finish
endpoint) own fetching the tunables so this module stays pure and trivially
unit-testable without a database.
"""

import math
from dataclasses import dataclass

DEFAULT_RUN_THRESHOLDS = ((5, 1.0), (10, 0.5), (20, 0.25))  # (runs_today < N, multiplier); else 0
DEFAULT_DAILY_GAME_XP_CAP = 1000


def level_for_xp(total_xp: int) -> int:
    """Inverse of xp_required_for_level: level = 1 + floor((xp/100)^(2/3)).

    Floating-point power-of-a-fraction (computed via log/exp under the hood)
    lands just under an exact integer at some thresholds — e.g. 8**(2/3)
    evaluates to 3.9999999999999996, not 4.0 — which would floor to one
    level below where a player should actually land right at a level
    boundary. A tiny epsilon absorbs that without affecting any other value
    (XP and levels are always integers, so there's no legitimate value this
    could incorrectly round up).
    """
    if total_xp <= 0:
        return 1
    return 1 + math.floor((total_xp / 100) ** (2 / 3) + 1e-9)


def xp_required_for_level(level: int) -> int:
    """XP required to *reach* level n: round(100 * (n-1)^1.5). Level 1 = 0 XP.

    Note: because this rounds to the nearest integer, it isn't a perfect
    inverse of level_for_xp() at every boundary — e.g. xp_required_for_level(6)
    == 1118, but level_for_xp(1118) == 5 (the true value before rounding was
    1118.03...). Verified this can only ever be off by one level, and only
    exactly at a rounded threshold value, never in a way that makes level
    regress as XP increases (see tests/test_xp.py). Not worth deviating from
    the plan's stated formulas to fix a sub-1-XP edge case.
    """
    if level <= 1:
        return 0
    return round(100 * (level - 1) ** 1.5)


def level_progress(total_xp: int, level: int) -> dict:
    """{current_level_xp, xp_for_next_level} — how far into the current
    level this XP total is. Shared by the finish/checkin/`/me` responses
    so the math only lives in one place."""
    base = xp_required_for_level(level)
    nxt = xp_required_for_level(level + 1)
    return {"current_level_xp": total_xp - base, "xp_for_next_level": nxt - base}


def diminishing_multiplier(runs_today: int, thresholds: tuple = DEFAULT_RUN_THRESHOLDS) -> float:
    for limit, multiplier in thresholds:
        if runs_today < limit:
            return multiplier
    return 0.0


@dataclass
class XpAward:
    base_xp: int
    multiplier: float
    xp: int


def compute_run_xp(
    score: int,
    xp_rate: float,
    max_xp_per_run: int,
    runs_today: int,
    game_xp_earned_today: int,
    daily_game_xp_cap: int = DEFAULT_DAILY_GAME_XP_CAP,
    thresholds: tuple = DEFAULT_RUN_THRESHOLDS,
) -> XpAward:
    base_xp = min(math.floor(score * xp_rate), max_xp_per_run)
    multiplier = diminishing_multiplier(runs_today, thresholds)
    xp = math.floor(base_xp * multiplier)
    remaining_cap = max(0, daily_game_xp_cap - game_xp_earned_today)
    xp = min(xp, remaining_cap)
    return XpAward(base_xp=base_xp, multiplier=multiplier, xp=xp)
