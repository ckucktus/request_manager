from typing import Type
from unittest.mock import Mock

import aioredis
import pytest

from src.rate_imiter.rate_limiter import RateLimitException, SlidingWindowRateLimiter




async def test_general_flow_sliding_window(redis_connection, clean_redis):
    with pytest.raises(RateLimitException) as exc:
        for _ in range(10):
            async with SlidingWindowRateLimiter(
                redis_connection=redis_connection, redis_key='unique_key', rate_for_minute=60, rate_for_second=1
            ):
                pass
    assert exc.value.args[0] == 'Limit exceeded, limit per second: 1 counted calls: 1'


@pytest.mark.parametrize(
    'second_rate,minute_rate,hour_rate,day_rate, result',
    [
        [1, 2, 3, 4, None],
        [2, 1, 2, 3, ValueError],
        [1, 3, 2, 3, ValueError],
        [1, 2, 4, 3, ValueError],
        [4, 1, 4, 3, ValueError],
        [1, 2, None, 4, None],
        [1, 5, None, 4, ValueError],
    ],
)
def test_check_validate_limit(
    second_rate: int,
    minute_rate: int,
    hour_rate: int,
    day_rate: int,
    result: Type[Exception],
):

    if result:
        with pytest.raises(result):
            SlidingWindowRateLimiter(
                Mock(),
                'mock_redis_key',
                rate_for_second=second_rate,
                rate_for_minute=minute_rate,
                rate_for_hour=hour_rate,
                rate_for_day=day_rate,
            )
    else:
        SlidingWindowRateLimiter(
            Mock(),
            'mock_redis_key',
            rate_for_second=second_rate,
            rate_for_minute=minute_rate,
            rate_for_hour=hour_rate,
            rate_for_day=day_rate,
        )
