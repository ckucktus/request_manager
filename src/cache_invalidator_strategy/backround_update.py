import asyncio
import inspect
from typing import Any, Callable, Coroutine, Dict, Optional, TYPE_CHECKING, Type, Union

from src.cache_invalidator_strategy.base import AbstractCacheStrategy, HelpUtilsMixin
from src.exceptions.exceptions import InvalidCacheError
from src.rate_imiter.rate_limiter import RateLimitException, SlidingWindowRateLimiter
from src.cache_manager.cache_manager import AbstractCacheService, CacheControlService
from contextlib import nullcontext
from tenacity import RetryError

if TYPE_CHECKING:
    from aioredis import ConnectionPool, Redis


class BackgroundUpdater(AbstractCacheStrategy, HelpUtilsMixin):
    def __init__(
        self,
        cache_service: AbstractCacheService,
        request_retryer: Optional[Callable] = None,
        rate_limiter: SlidingWindowRateLimiter = None,
        use_cache: bool = True,  # TODO пересмотреть целесообразность этого параметра
        **kwargs: Any,
    ) -> None:
        self.request_retryer = request_retryer
        self.rate_limiter = rate_limiter
        self.use_cache = use_cache
        self.cache_service: AbstractCacheService = cache_service
        self.kwargs = kwargs

    async def get_data_with_cache(self, redis_key: str, wrapped_func: Callable[[Any, Any], Any]) -> Any:
        result = None  # todo sentinel
        executor = self.build_executor(wrapped_func, self.request_retryer, self.rate_limiter)

        try:
            result = await self.cache_service.get_cache(redis_key)
        except InvalidCacheError:
            result = None

        if result:
            asyncio.create_task(self._update_cache(wrapped_func, redis_key))
            return result

        try:
            result = await executor(wrapped_func, redis_key)
        except RateLimitException:
            executor_without_rate_limit = self.build_executor(
                wrapped_func, request_retryer=self.request_retryer, rate_limiter=None
            )  # при отсутствии кэша, все равно следует отдать результат
            result = await executor_without_rate_limit(wrapped_func, redis_key)
            if result:
                asyncio.create_task(self.cache_service.set_cache(redis_key, result))
        if result:
            asyncio.create_task(self.cache_service.set_cache(redis_key=redis_key, data=result))
            await asyncio.sleep(0)

            # await self.cache_service.set_cache(redis_key=redis_key, data=result)

            return result

        return result

    async def get_data(self, wrapped_func: Callable, redis_key: str, **kwargs) -> Any:
        if self.use_cache:
            return await self.get_data_with_cache(redis_key, wrapped_func)
        return self.get_data_without_cache()

    async def _update_cache(self, wrapped_func: Callable, redis_key: str) -> Any:
        executor = self._build_executor(wrapped_func, self.request_retryer, self.rate_limiter)
        try:
            data = await executor(wrapped_func, redis_key)
        except (RateLimitException, RetryError):  # todo непонятно как тут можно убрать связанность
            return
        await self.cache_service.set_cache(redis_key=redis_key, data=data)
