"""Test fixtures.

Plan section 18 recommends testcontainers for integration tests (spins up
real Postgres/Redis in Docker per test run). Not usable in the environment
these tests were originally written in: the docker daemon here has no
outbound network access, so `docker pull` for the postgres/redis images
never completes. Falls back to a dedicated local Postgres database
(`alphago_test`, created once via `createdb`) instead — still a real
Postgres, just not a throwaway container. A CI environment with working
Docker networking should be able to switch this to testcontainers with
minimal changes (only this file would need to change).
"""

import os
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core import db as db_module
from app.core import redis as redis_module

# Overridable via env (CI's Postgres service container uses different
# credentials than this environment's local peer-auth role) — falls back
# to the same local default this was always hardcoded to.
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "postgresql+asyncpg://ramsi@/alphago_test")


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    # NullPool: a pooled connection can otherwise get checked out by one
    # coroutine (the test's own db_session) while still "in flight" from
    # another (a request handled through the app's separate session
    # factory), which asyncpg surfaces as "another operation is in
    # progress" rather than SQLAlchemy serializing access the way it does
    # with a sync driver. A fresh connection per checkout sidesteps it —
    # fine for tests; production should keep real pooling (PgBouncer per
    # plan section 19 once there are multiple API instances).
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(db_module.Base.metadata.drop_all)
        await conn.run_sync(db_module.Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()
        # Truncate everything between tests so they don't see each other's rows.
        async with test_engine.begin() as conn:
            for table in reversed(db_module.Base.metadata.sorted_tables):
                await conn.execute(table.delete())


@pytest.fixture
def fake_redis():
    """Clears get_redis()'s lru_cache so every test gets a fresh, isolated
    FakeAsyncRedis instance. Deliberately NOT done via monkeypatching the
    `get_redis` name itself: several modules do `from app.core.redis import
    get_redis`, which binds their own reference to the original function at
    import time — replacing the attribute on `redis_module` afterward
    wouldn't reach those call sites. Clearing the cache instead means the
    real get_redis() re-executes and builds a new instance, which every
    caller sees identically because they're all calling the same
    lru_cache-wrapped function, just with a cleared cache.
    """
    redis_module.get_redis.cache_clear()
    return redis_module.get_redis()


@pytest_asyncio.fixture
async def client(test_engine, db_session, fake_redis) -> AsyncGenerator[AsyncClient, None]:
    """An httpx client wired to the real FastAPI app, but pointed at the
    test database/session and a fresh fakeredis instance per test."""
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)

    async def override_get_db():
        async with session_factory() as session:
            yield session

    from app.main import app

    app.dependency_overrides[db_module.get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

    app.dependency_overrides.clear()
