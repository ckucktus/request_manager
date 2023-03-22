from functools import partial
from typing import Any

from src.cache_invalidator_strategy.base import AbstractCacheStrategy, HelpUtilsMixin
from src.cache_manager.cache_manager import BaseCacheControlService


class TTLInvalidator(AbstractCacheStrategy, HelpUtilsMixin):
    def __init__(
        self,
        cache_service: BaseCacheControlService,
        use_retry: bool = False,
        **kwargs: Any,
    ) -> None:
        self.use_retry = use_retry
        self.cache_service = cache_service
        self.kwargs = kwargs

    async def get_data(
        self,
        wrapped_func: partial,
        cache_key: str,
    ) -> Any:
        executor = self.build_executor(
            cache_key=cache_key,
            use_retry=self.use_retry,
            use_rate_limiter=False,
            **self.kwargs,
        )
        cache = await self.cache_service.get_cache(cache_key)
        if cache:
            return cache
        result = await executor(wrapped_func)
        if result:
            await self.cache_service.set_cache(cache_key, result)

        return result
