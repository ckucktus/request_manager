from contextlib import AbstractAsyncContextManager
from time import time
from typing import Any, Callable, List

from aioredis import Redis
from aioredis.client import Pipeline

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
        cache_key: str,
        rate_for_second: int = None,
        rate_for_minute: int = None,
        rate_for_hour: int = None,
        rate_for_day: int = None,
    ) -> None:
        self.redis_connection = redis_connection
        self.cache_key = cache_key + ':rate_limiter'
        self.rate_for_second = rate_for_second
        self.rate_for_minute = rate_for_minute
        self.rate_for_hour = rate_for_hour
        self.rate_for_day = rate_for_day
        self._validate_limits()

        self.request_time: float = time()

    def _validate_limits(self) -> None:

        limits: List[int] = list(
            filter(bool, [self.rate_for_second, self.rate_for_minute, self.rate_for_hour, self.rate_for_day])
        )
        for i, current_limit in enumerate(limits):
            for higher_limit in limits[i + 1 :]:
                if current_limit > higher_limit:
                    raise ValueError

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

        pipline.zremrangebylex(self.cache_key, min="-", max=f"[{int(self.request_time)-window_max_size}")
        pipline.zlexcount(self.cache_key, min=f"[{self.request_time-SECOND}", max=f"[{self.request_time + 1}")
        pipline.zlexcount(self.cache_key, min=f"[{self.request_time-MINUTE}", max=f"[{self.request_time + 1}")
        pipline.zlexcount(self.cache_key, min=f"[{self.request_time-HOUR}", max=f"[{self.request_time + 1}")
        pipline.zlexcount(self.cache_key, min=f"[{self.request_time-DAY}", max=f"[{self.request_time + 1}")

        return pipline

    async def __aenter__(self) -> None:
        """
        Используется алгоритм скользящего на основе редиса
        Размер окна - максимальный лимит
        работает на упорядоченном множестве с лексикографической сортировкой

        ключ(float значение, float значение}

        Пример
        множество в редисе:
        лимит указан не более 2 раз в секунду
        lk_simi-get_document_patient_id=1(1663865143.2675214, 1663865143.3675214}

        в это время происходит запрос с timestamp 1663865143.5
        Запрос не пройдет так как в последнюю секунду уже было сделано 2 запроса
        """

        pipeline = self._build_getter_pipeline()
        _, last_second_count, last_minute_count, last_hour_count, last_day_count = await pipeline.execute()
        self._check_limit(last_second_count, last_minute_count, last_hour_count, last_day_count)

    def __call__(self, func: Callable) -> Callable:
        async def wrapped(*args: Any, **kwargs: Any) -> Any:
            pipeline = self._build_getter_pipeline()

            _, last_second_count, last_minute_count, last_hour_count, last_day_count = await pipeline.execute()
            self._check_limit(last_second_count, last_minute_count, last_hour_count, last_day_count)
            try:
                return await func(*args, **kwargs)
            finally:
                await self.redis_connection.zadd(
                    self.cache_key,
                    {f"{self.request_time}": 0},
                )

        return wrapped

    async def __aexit__(self, *exc: Any) -> None:
        """
        При выходе и контекста происходит запись в редис с временной меткой запроса,
        временем считается момент закрытия контекста
        """
        await self.redis_connection.zadd(
            self.cache_key,
            {f"{self.request_time}": 0},
        )
