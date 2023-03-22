import asyncio
from datetime import datetime, timezone
from typing import Any, Callable

from main import RequestManager
from src.cache_invalidator_strategy.backround_update import BackgroundUpdater
from src.cache_manager.cache_manager import CacheControlService
from src.rate_imiter.rate_limiter import SlidingWindowRateLimiter


class FakeRequestManager(RequestManager):
    def build_cache_key(
        self,
        func: Callable,
        *func_call_args: Any,
        **func_call_kwargs: Any,
    ) -> str:
        key = super().build_cache_key(func, *func_call_args, **func_call_kwargs)
        return key + datetime.now(tz=timezone.utc).isoformat()


async def test_get_data_with_cache_without_retry(redis_connection, clean_redis):
    manager = FakeRequestManager(
        service_name='test_service',
        service_version='test_version',
        cache_strategy=BackgroundUpdater(
            cache_service=CacheControlService(redis_connection),
            rate_limiter=SlidingWindowRateLimiter,
            redis_connection=redis_connection,
        ),
    )

    async def perform_request(arg):
        perform_request.call_count += 1
        return arg

    TEST_DATA = 'integrator_data'

    perform_request.call_count = 0

    wrapped_perform_request = manager(perform_request)

    result_without_cache = await wrapped_perform_request(TEST_DATA)
    assert result_without_cache == TEST_DATA
    assert perform_request.call_count == 1
    await asyncio.sleep(1)  # ждем пока выполнится установка кэша в фоне

    result_from_cache = await wrapped_perform_request(TEST_DATA)
    assert result_from_cache == TEST_DATA
    await asyncio.sleep(1)  # ждем пока выполнится обновление кэша в фоне
    assert perform_request.call_count == 2

    key = RequestManager.build_cache_key(manager, perform_request, TEST_DATA)

    _, keys = await redis_connection.scan(match=key + '*')
    assert len(keys) == 2


async def test_get_data_with_cache_blocked_by_rate_limiter_without_retry(redis_connection, clean_redis):
    manager = RequestManager(
        service_name='test_service',
        service_version='test_version',
        cache_strategy=BackgroundUpdater(
            cache_service=CacheControlService(redis_connection),
            use_rate_limiter=True,
            redis_connection=redis_connection,
        ),
    )

    async def perform_request(arg):
        perform_request.call_count += 1
        return arg

    TEST_DATA = 'integrator_data'
    perform_request.call_count = 0

    wrapped_perform_request = manager(perform_request)

    result_without_cache = await wrapped_perform_request(TEST_DATA)
    assert result_without_cache == TEST_DATA
    assert perform_request.call_count == 1
    await asyncio.sleep(1)  # ждем пока выполнится установка кэша в фоне

    result_from_cache = await wrapped_perform_request(TEST_DATA)
    assert result_from_cache == TEST_DATA
    await asyncio.sleep(1)  # ждем пока выполнится обновление кэша в фоне
    assert perform_request.call_count == 2

    key = RequestManager.build_cache_key(manager, perform_request, TEST_DATA)

    _, keys = await redis_connection.scan(match=key + '*')
    assert len(keys) == 2
