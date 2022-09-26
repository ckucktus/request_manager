from aioredis import Redis
import aioredis
import pytest


@pytest.fixture
async def redis_connection():
    pool = aioredis.ConnectionPool.from_url("redis://localhost:6379", decode_responses=True, db=1)

    yield Redis(connection_pool=pool)

    await pool.disconnect()


@pytest.fixture
async def clean_redis(redis_connection):
    yield
    await redis_connection.flushdb()
