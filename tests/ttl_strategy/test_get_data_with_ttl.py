import asyncio
from datetime import datetime, timezone
from typing import Any, Callable

from main import RequestManager
from src.cache_invalidator_strategy import TTLInvalidator
from src.cache_manager.cache_manager import BaseCacheControlService


class FakeCacheControlService(BaseCacheControlService):
    def build_redis_key(
        self,
        func: Callable,
        *func_call_args: Any,
        **func_call_kwargs: Any,
    ) -> str:
        return func.__name__ + datetime.now(tz=timezone.utc).isoformat()


async def test_get_data_with_ttl(redis_connection, clean_redis):
    @RequestManager(
        service_name='test_service',
        service_version='test_version',
        cache_strategy=TTLInvalidator(
            cache_service=FakeCacheControlService(redis_connection, px=200),
        ),
    )
    async def perform_request(arg):
        perform_request.call_count += 1
        return arg

    TEST_DATA = 'integrator_data'
    perform_request.call_count = 0

    assert await perform_request(TEST_DATA) == TEST_DATA
    assert perform_request.call_count == 1

    assert await perform_request(TEST_DATA) == TEST_DATA
    assert perform_request.call_count == 1

    await asyncio.sleep(0.5)

    assert await perform_request(TEST_DATA) == TEST_DATA
    assert perform_request.call_count == 2
