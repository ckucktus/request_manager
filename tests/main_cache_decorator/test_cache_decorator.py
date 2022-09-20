from unittest.mock import AsyncMock, Mock

import pytest
from tenacity import AsyncRetrying, retry

from main import UsingCache, dummy_decorator
from src.rate_imiter.rate_limiter import SlidingWindowRateLimiter
from src.request_retryer.request_retryer import RequestRetryer


@pytest.mark.parametrize(
    'request_retryer,rate_limiter,retryier_expected',
    [
        [retry, SlidingWindowRateLimiter, AsyncRetrying],
        [None, None, type(None)],
        [retry, None, AsyncRetrying],
        [None, SlidingWindowRateLimiter, type(None)],
    ],
)
async def test_building_executor(request_retryer, rate_limiter, retryier_expected):
    cache_instance = UsingCache(
        service_name='test', redis_connection=Mock(), request_retryer=request_retryer, rate_limiter=rate_limiter
    )

    async def perform_request(data):
        pass

    executor = cache_instance._build_executor(perform_request, request_retryer, rate_limiter)

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
        [Mock(return_value=retry), LimiterMock(), EmptyRetryer(return_value=dummy_decorator()), EmptyLimiterMock()],
        [
            Mock(return_value=retry),
            EmptyLimiterMock(),
            EmptyRetryer(return_value=dummy_decorator()),
            EmptyLimiterMock(),
        ],
        [
            EmptyRetryer(return_value=dummy_decorator()),
            EmptyLimiterMock(),
            EmptyRetryer(return_value=dummy_decorator()),
            EmptyLimiterMock(),
        ],
        [
            EmptyRetryer(return_value=dummy_decorator()),
            LimiterMock(),
            EmptyRetryer(return_value=dummy_decorator()),
            EmptyLimiterMock(),
        ],
    ],
)
async def test_executor_behavior_all(request_retryer, rate_limiter, missed_request_retryer, missed_rate_limiter):
    expected_result = 1
    cache_instance = UsingCache(
        service_name='test', redis_connection=Mock(), rate_limiter=rate_limiter, request_retryer=request_retryer
    )

    async def perform_request(*args, **kwargs):
        return args[0]

    executor = cache_instance._build_executor(
        perform_request,
        request_retryer=request_retryer,
        rate_limiter=rate_limiter,
        missed_request_retryer=missed_request_retryer,
        missed_rate_limiter=missed_rate_limiter
    )
    r = await executor(perform_request, 'unique_redis_key', expected_result)

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
