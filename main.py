from __future__ import annotations

from functools import partial
from typing import Any, Callable, TYPE_CHECKING

from src.cache_invalidator_strategy.base import AbstractCacheStrategy, HelpUtilsMixin
from src.cache_manager.cache_manager import AbstractCacheService


class RequestManager:
    def __init__(self, cache_strategy: AbstractCacheStrategy, cache_service: AbstractCacheService) -> None:
        self.cache_strategy = cache_strategy
        self.cache_service = cache_service

    def __call__(self, func: Callable) -> Callable:

        async def wrapped(*args: Any, **kwargs: Any) -> Any:
            redis_key = self.cache_service.build_redis_key(func, *args, **kwargs)
            wrapped_func = partial(func, *args, **kwargs)

            return await self.cache_strategy.get_data(wrapped_func, redis_key)

        return wrapped
