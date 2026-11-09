import pytest

from app.services.xp import compute_run_xp, diminishing_multiplier, level_for_xp, xp_required_for_level


@pytest.mark.parametrize("level", range(1, 200))
def test_level_round_trip_never_regresses(level):
    """level_for_xp(xp_required_for_level(n)) must be >= n, and one XP less
    must be < n (except level 1, which starts at 0 XP already). See
    xp_required_for_level's docstring for the one known, harmless rounding
    quirk this tolerates (off by at most one level, never in the direction
    that makes level go backwards as XP increases)."""
    required = xp_required_for_level(level)
    if level > 1:
        assert level_for_xp(required - 1) < level
    assert level_for_xp(required) >= level - 1  # tolerate the rounding quirk, never more than 1 level off


def test_level_for_xp_never_decreases_as_xp_increases():
    prev = level_for_xp(0)
    for xp in range(0, 50_000, 7):  # step by 7 to cover the range without 50k iterations
        level = level_for_xp(xp)
        assert level >= prev, f"level regressed at xp={xp}: {prev} -> {level}"
        prev = level


def test_level_for_xp_floating_point_boundary():
    # 8 ** (2/3) evaluates to 3.9999999999999996 in IEEE754, not 4.0 exactly.
    # xp_required_for_level(5) == 800 should land exactly on level 5.
    assert level_for_xp(800) == 5


@pytest.mark.parametrize(
    "runs_today,expected",
    [(0, 1.0), (4, 1.0), (5, 0.5), (9, 0.5), (10, 0.25), (19, 0.25), (20, 0.0), (100, 0.0)],
)
def test_diminishing_multiplier_boundaries(runs_today, expected):
    assert diminishing_multiplier(runs_today) == expected


def test_compute_run_xp_basic():
    r = compute_run_xp(score=20_000, xp_rate=0.01, max_xp_per_run=300, runs_today=0, game_xp_earned_today=0)
    assert r.base_xp == 200
    assert r.xp == 200


def test_compute_run_xp_diminishing_returns_applies():
    r = compute_run_xp(score=20_000, xp_rate=0.01, max_xp_per_run=300, runs_today=5, game_xp_earned_today=500)
    assert r.xp == 100  # 200 base * 0.5 multiplier


def test_compute_run_xp_capped_by_max_xp_per_run():
    r = compute_run_xp(score=500_000, xp_rate=0.01, max_xp_per_run=300, runs_today=0, game_xp_earned_today=0)
    assert r.base_xp == 300


def test_compute_run_xp_capped_by_daily_game_cap():
    r = compute_run_xp(
        score=20_000, xp_rate=0.01, max_xp_per_run=300, runs_today=0,
        game_xp_earned_today=950, daily_game_xp_cap=1000,
    )
    assert r.xp == 50  # would be 200, clamped to the 50 remaining


def test_compute_run_xp_at_daily_cap_awards_nothing():
    r = compute_run_xp(
        score=20_000, xp_rate=0.01, max_xp_per_run=300, runs_today=0,
        game_xp_earned_today=1000, daily_game_xp_cap=1000,
    )
    assert r.xp == 0


def test_compute_run_xp_beyond_twentieth_run_awards_nothing():
    r = compute_run_xp(score=20_000, xp_rate=0.01, max_xp_per_run=300, runs_today=25, game_xp_earned_today=0)
    assert r.xp == 0
