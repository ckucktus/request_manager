import asyncio
import functools
import threading
from asyncio import AbstractEventLoop
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Any, Callable, Coroutine, Dict, Optional, Type

from tenacity import RetryError

from src.cache_invalidator_strategy.base import AbstractCacheStrategy, HelpUtilsMixin
from src.cache_manager.cache_manager import AbstractCacheService
from src.exceptions.exceptions import InvalidCacheError
from src.rate_imiter.rate_limiter import RateLimitException, SlidingWindowRateLimiter

if TYPE_CHECKING:
    pass
from aioredis import Redis


class Singleton(type):
    _instances: Dict = {}

    def __call__(cls, *args: Any, **kwargs: Any) -> Type:
        if cls not in cls._instances:
            cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]


class BackgroundUpdater(AbstractCacheStrategy, HelpUtilsMixin):
    def __init__(
        self,
        cache_service: AbstractCacheService,
        redis_connection: Redis,
        request_retryer: Optional[Callable] = None,
        rate_limiter: Type[SlidingWindowRateLimiter] = None,
        use_cache: bool = True,
        **kwargs: Any,
    ) -> None:
        self.redis_connection = redis_connection
        self.cache_service = cache_service
        self.request_retryer = request_retryer
        self.rate_limiter = rate_limiter
        self.use_cache = use_cache
        self.kwargs = kwargs

    async def run_background_coro(self, coro: Coroutine) -> None:
        def background_task(loop: AbstractEventLoop, _coro: Coroutine) -> None:
            future = asyncio.run_coroutine_threadsafe(_coro, loop=loop)
            future.result()

        target = functools.partial(
            background_task,
            loop=asyncio.get_running_loop(),
            _coro=coro,
        )
        threading.Thread(target=target).start()

    async def get_data_with_cache(self, wrapped_func: functools.partial, cache_key: str) -> Any:
        executor = self.build_executor(
            request_retryer=self.request_retryer,
            rate_limiter=self.rate_limiter,
            cache_key=cache_key,
            redis_connection=self.redis_connection,
            **self.kwargs,
        )

        try:
            result = await self.cache_service.get_cache(cache_key)
        except InvalidCacheError:
            result = None  # todo sentinel

        if result:
            await self.run_background_coro(self._update_cache(executor, wrapped_func, cache_key))
            return result

        try:
            result = await executor(wrapped_func)
        except RateLimitException:
            executor_without_rate_limit = self.build_executor(
                redis_connection=self.redis_connection,
                cache_key=cache_key,
                request_retryer=self.request_retryer,
                rate_limiter=None,
                **self.kwargs,
            )  # при отсутствии кэша, все равно следует отдать результат
            result = await executor_without_rate_limit(wrapped_func)
            if result:
                await self.run_background_coro(self.cache_service.set_cache(redis_key=cache_key, data=result))
                return result
        if result:
            await self.run_background_coro(self.cache_service.set_cache(redis_key=cache_key, data=result))
            return result

        return result

    async def get_data(self, wrapped_func: functools.partial, cache_key: str, use_cache: bool = True) -> Any:
        if use_cache:
            return await self.get_data_with_cache(wrapped_func, cache_key)
        return self.get_data_without_cache()

    async def _update_cache(self, executor, wrapped_func: Callable, cache_key: str) -> Any:

        try:
            data = await executor(wrapped_func)
        except (RateLimitException, RetryError):  # todo непонятно как тут можно убрать связанность
            return
        await self.cache_service.set_cache(redis_key=cache_key, data=data)


pool = ThreadPoolExecutor()
