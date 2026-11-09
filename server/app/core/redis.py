"""Redis client factory.

Production should point REDIS_URL at a real Redis 7 instance (plan section
2). This dev environment has neither a Redis server nor a way to install
one (no sudo, no network reachable from the docker daemon for `docker pull`)
— so REDIS_URL defaults to the "fakeredis://" sentinel, which this module
swaps for an in-memory, protocol-compatible fake. All leaderboard/rate-limit
code should go through this client and never care which backend it got;
switching to real Redis anywhere else is just an env var change.
"""

from functools import lru_cache

import redis.asyncio as real_redis
from fakeredis import FakeAsyncRedis

from app.core.config import settings


@lru_cache
def get_redis():
    if settings.redis_url == "fakeredis://":
        return FakeAsyncRedis(decode_responses=True)
    return real_redis.from_url(settings.redis_url, decode_responses=True)
