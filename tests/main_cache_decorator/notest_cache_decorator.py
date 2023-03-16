from functools import partial
from typing import Callable, Optional
from unittest.mock import AsyncMock, Mock

import pytest
from tenacity import AsyncRetrying, retry

from main import RequestManager
from src.rate_imiter.rate_limiter import SlidingWindowRateLimiter


@pytest.mark.parametrize(
    'request_retryer,rate_limiter,retryier_expected',
    [
        [retry, SlidingWindowRateLimiter, AsyncRetrying],
        [None, None, type(None)],
        [retry, None, AsyncRetrying],
        [None, SlidingWindowRateLimiter, type(None)],
    ],
)
async def test_building_executor(
    request_retryer: Optional[Callable], rate_limiter: Optional[SlidingWindowRateLimiter], retryier_expected
):
    rate_limiter = rate_limiter(redis_connection=Mock(), redis_key='redis_key') if rate_limiter is not None else None
    cache_instance = RequestManager(service_version='1.1', service_name='test', redis_connection=Mock())

    async def perform_request(data):
        pass

    wrapped_func = partial(perform_request, 'data')

    executor = cache_instance._build_executor(wrapped_func, request_retryer, rate_limiter)

    assert isinstance(executor.retry, retryier_expected)


class LimiterMock(AsyncMock):
    def __call__(self, *args, **kwargs):
        return self

    __aenter__ = AsyncMock()
    __aexit__ = AsyncMock()


class EmptyLimiterMock(LimiterMock):
    def __bool__(self):
        return False


class EmptyRetryer(Mock):
    def __bool__(self):
        return False


@pytest.mark.parametrize(
    'request_retryer,rate_limiter,missed_request_retryer,missed_rate_limiter',
    [
        pytest.param(
            Mock(return_value=retry),
            LimiterMock(),
            EmptyRetryer(return_value=dummy_decorator()),
            EmptyLimiterMock(),
            id='retryer_on_limiter_off',
        ),
        # [
        #     Mock(return_value=retry),
        #     EmptyLimiterMock(),
        #     EmptyRetryer(return_value=dummy_decorator()),
        #     EmptyLimiterMock(),
        # ],
        # [
        #     EmptyRetryer(return_value=dummy_decorator()),
        #     EmptyLimiterMock(),
        #     EmptyRetryer(return_value=dummy_decorator()),
        #     EmptyLimiterMock(),
        # ],
        # [
        #     EmptyRetryer(return_value=dummy_decorator()),
        #     LimiterMock(),
        #     EmptyRetryer(return_value=dummy_decorator()),
        #     EmptyLimiterMock(),
        # ],
    ],
)
async def test_executor_behavior_all(request_retryer, rate_limiter, missed_request_retryer, missed_rate_limiter):
    expected_result = 1
    cache_instance = RequestManager(
        service_name='test', redis_connection=Mock(), rate_limiter=rate_limiter, request_retryer=request_retryer
    )

    async def perform_request(*args, **kwargs):
        return expected_result

    wrapped_func = partial(perform_request, 'test')

    executor = cache_instance._build_executor(
        wrapped_func,
        request_retryer=request_retryer,
        rate_limiter=rate_limiter,
        missed_request_retryer=missed_request_retryer,
        missed_rate_limiter=missed_rate_limiter,
    )
    r = await executor(wrapped_func, 'unique_redis_key')

    assert r == expected_result
    if rate_limiter:
        assert rate_limiter.__aenter__.called and rate_limiter.__aexit__.called
        assert not (missed_rate_limiter.__aenter__.called and missed_rate_limiter.__aexit__.called)
    else:
        assert not (rate_limiter.__aenter__.called and rate_limiter.__aexit__.called)
        assert missed_rate_limiter.__aenter__.called and missed_rate_limiter.__aexit__.called

    if request_retryer:
        assert request_retryer.called
        assert not missed_request_retryer.called
    else:
        assert not request_retryer.called
        assert missed_request_retryer.called
