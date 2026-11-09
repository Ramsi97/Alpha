"""Redis leaderboards (plan section 10).

Runs against whatever app.core.redis.get_redis() returns — fakeredis in
this dev environment, real Redis wherever this actually deploys. Postgres
(`scores`, `xp_events`) stays the source of truth; everything here is
rebuildable from those tables (rebuild job is a later-phase TODO, not built
in this pass — flag it before relying on this in production long-term).
"""

import time

_TIE_BREAK_CUTOFF = 9_999_999_999  # ~year 2286; just needs to exceed any real epoch second


def _tie_break_fraction(now: float | None = None) -> float:
    """Earlier timestamps get a larger fraction, so among equal integer
    scores, whoever got there first ranks higher (plan section 10)."""
    now = now if now is not None else time.time()
    return max(0.0, (_TIE_BREAK_CUTOFF - now) / _TIE_BREAK_CUTOFF)


def game_leaderboard_key(game_id: int, variant: str | None) -> str:
    return f"lb:game:{game_id}:{variant or '_'}:best"


def xp_leaderboard_key() -> str:
    return "lb:xp:global"


async def record_game_score(redis, user_id: int, game_id: int, variant: str | None, score: int) -> None:
    key = game_leaderboard_key(game_id, variant)
    member_score = float(score) + _tie_break_fraction()
    await redis.zadd(key, {str(user_id): member_score}, gt=True)


async def record_total_xp(redis, user_id: int, total_xp: int) -> None:
    await redis.zadd(xp_leaderboard_key(), {str(user_id): float(total_xp)})


async def get_rank(redis, key: str, user_id: int) -> int | None:
    rank = await redis.zrevrank(key, str(user_id))
    return None if rank is None else rank + 1  # 1-based for display


async def get_top(redis, key: str, n: int = 100) -> list[tuple[int, float]]:
    rows = await redis.zrevrange(key, 0, n - 1, withscores=True)
    return [(int(member), score) for member, score in rows]
