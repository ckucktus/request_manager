from functools import partial
from typing import Any, Callable, Optional

from aioredis import Redis

from ..cache_manager.cache_manager import CacheControlService
from .base import AbstractCacheStrategy, HelpUtilsMixin


class TTLInvalidator(AbstractCacheStrategy, HelpUtilsMixin):
    def __init__(
        self,
        redis_connection: Redis,
        cache_service: CacheControlService,
        request_retryer: Optional[Callable] = None,
        **kwargs: Any,
    ) -> None:
        self.request_retryer = request_retryer
        self.cache_service = cache_service
        self.redis_connection = redis_connection
        self.kwargs = kwargs

    async def get_data(
        self,
        wrapped_func: partial,
        cache_key: str,
        use_cache: bool = True,  # для тестирования
    ) -> Any:
        executor = self.build_executor(
            cache_key=cache_key,
            redis_connection=self.redis_connection,
            request_retryer=self.request_retryer,
            rate_limiter=None,
            **self.kwargs,
        )
        cache = None

        if use_cache:
            cache = self.cache_service.get_cache(cache_key)
        if cache:
            return cache
        result = await executor(wrapped_func)
        if result:
            await self.cache_service.set_cache(cache_key, result)

        return result
