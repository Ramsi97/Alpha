"""Redis-backed rate limiting (plan section 17).

Fixed-window counters, not a true sliding window — simpler, and good
enough at this scale (plan section 20 estimates 20-30 req/s peak).
"""

import hashlib

from fastapi import Depends, Request

from app.core.errors import ApiError
from app.core.redis import get_redis


def _hash_identity(identity: str) -> str:
    # sha256, not Python's built-in hash(): that's randomized per process
    # (PYTHONHASHSEED), so the same identity would land in different
    # buckets on different API instances once this runs behind more than
    # one process (plan section 19 growth path).
    return hashlib.sha256(identity.encode()).hexdigest()[:16]


async def _check_and_increment(key_prefix: str, identity: str, limit: int, window_seconds: int) -> None:
    key = f"ratelimit:{key_prefix}:{_hash_identity(identity)}"
    redis = get_redis()
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, window_seconds)
    if count > limit:
        raise ApiError(429, "rate_limited", f"Too many requests. Limit is {limit} per {window_seconds}s.")


def rate_limit(key_prefix: str, limit: int, window_seconds: int):
    """Returns a FastAPI dependency enforcing `limit` calls per
    `window_seconds` per authenticated user (plan section 17's per-user
    limits: session starts, finish calls, task verifies, auth)."""

    async def _dep(request: Request) -> None:
        # Routes using this depend on get_current_user too (for the real
        # auth check); here we only need *a* stable identity for the
        # counter key, and the user isn't resolved yet at dependency-
        # ordering time in every route, so key on the raw Authorization
        # header instead of re-decoding the JWT — cheap, and collisions
        # just mean two of the user's own requests share a bucket, which
        # is harmless. Routes with no auth yet (e.g. /auth/telegram) fall
        # back to client IP, so anonymous callers don't all share one
        # global bucket.
        identity = request.headers.get("authorization") or f"ip:{request.client.host if request.client else 'unknown'}"
        await _check_and_increment(key_prefix, identity, limit, window_seconds)

    return Depends(_dep)


def rate_limit_per_ip(key_prefix: str, limit: int, window_seconds: int):
    """A second, independent limit keyed on client IP regardless of auth
    state — catches "many accounts, one IP" abuse that a per-user limit
    alone can't (plan section 17: "Rate limits: ... per user **and IP**").
    Meant to be combined with rate_limit() on the same route via
    `dependencies=[...]`, not used alone."""

    async def _dep(request: Request) -> None:
        ip = request.client.host if request.client else "unknown"
        await _check_and_increment(f"{key_prefix}:ip", ip, limit, window_seconds)

    return Depends(_dep)
