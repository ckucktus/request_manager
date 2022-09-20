from time import time
from typing import Any, List

from aioredis import Redis
from aioredis.client import Pipeline
from contextlib import AbstractAsyncContextManager

DAY = 86400
HOUR = 3600
MINUTE = 60
SECOND = 1


class RateLimitException(Exception):
    pass


class SlidingWindowRateLimiter(AbstractAsyncContextManager):
    def __init__(
        self,
        redis_connection: Redis,
        redis_key: str,
        rate_for_second: int = None,
        rate_for_minute: int = None,
        rate_for_hour: int = None,
        rate_for_day: int = None,
    ) -> None:
        self.redis_connection = redis_connection
        self.redis_key = redis_key
        self.rate_for_second = rate_for_second
        self.rate_for_minute = rate_for_minute
        self.rate_for_hour = rate_for_hour
        self.rate_for_day = rate_for_day
        self._validate_limits()

        self.request_time: float = time()

        self.getter_pipeline = self._build_getter_pipeline()

    def _validate_limits(self) -> None:

        limits: List[int] = list(
            filter(bool, [self.rate_for_second, self.rate_for_minute, self.rate_for_hour, self.rate_for_day])
        )
        for i, current_limit in enumerate(limits):
            for higher_limit in limits[i + 1 :]:
                if current_limit > higher_limit:
                    raise ValueError

    def _build_getter_pipeline(self) -> Pipeline:
        pipline = self.redis_connection.pipeline()
        window_max_size = HOUR

        for sited_rate, window_size in zip(
            [self.rate_for_day, self.rate_for_hour, self.rate_for_minute, self.rate_for_second],
            [DAY, HOUR, MINUTE, SECOND],
        ):
            if sited_rate:
                window_max_size = window_size
                break

        pipline.zremrangebylex(self.redis_key, min="-", max=f"[{int(self.request_time)-window_max_size}")
        pipline.zlexcount(self.redis_key, min=f"[{self.request_time-SECOND}", max=f"[{self.request_time + 1}")
        pipline.zlexcount(self.redis_key, min=f"[{self.request_time-MINUTE}", max=f"[{self.request_time + 1}")
        pipline.zlexcount(self.redis_key, min=f"[{self.request_time-HOUR}", max=f"[{self.request_time + 1}")
        pipline.zlexcount(self.redis_key, min=f"[{self.request_time-DAY}", max=f"[{self.request_time + 1}")

        return pipline

    def _check_limit(
        self,
        last_second_count: int,
        last_minute_count: int,
        last_hour_count: int,
        last_day_count: int,
    ) -> None:
        if self.rate_for_second and last_second_count >= self.rate_for_second:
            raise RateLimitException(
                f'Limit exceeded, limit per second: {self.rate_for_second} counted calls: {last_second_count}'
            )

        if self.rate_for_minute and last_minute_count >= self.rate_for_minute:
            raise RateLimitException(
                f'Limit exceeded, limit per minute: {self.rate_for_minute} counted calls: {last_minute_count}'
            )

        if self.rate_for_hour and last_hour_count >= self.rate_for_hour:
            raise RateLimitException(
                f'Limit exceeded, limit per hour: {self.rate_for_hour} counted calls: {last_hour_count}'
            )

        if self.rate_for_day and last_day_count >= self.rate_for_day:
            raise RateLimitException(
                f'Limit exceeded, limit per second: {self.rate_for_day} counted calls: {last_day_count}'
            )

    async def __aenter__(self) -> None:
        """Используется упорядоченное множество с лексикографической сортировкой"""

        _, last_second_count, last_minute_count, last_hour_count, last_day_count = await self.getter_pipeline.execute()
        self._check_limit(last_second_count, last_minute_count, last_hour_count, last_day_count)

    async def __aexit__(self, *exc: Any) -> None:
        await self.redis_connection.zadd(
            self.redis_key,
            {f"{self.request_time}": 0},
        )
