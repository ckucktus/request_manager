import asyncio
import functools
import threading
from asyncio import AbstractEventLoop
from typing import TYPE_CHECKING, Any, Callable, Coroutine

from tenacity import RetryError

from src.cache_invalidator_strategy.base import AbstractCacheStrategy, HelpUtilsMixin
from src.cache_manager.cache_manager import BaseCacheControlService
from src.exceptions.exceptions import InvalidCacheError
from src.rate_imiter.rate_limiter import RateLimitException

if TYPE_CHECKING:
    pass
from aioredis import Redis


class BackgroundUpdater(AbstractCacheStrategy, HelpUtilsMixin):
    def __init__(
        self,
        cache_service: BaseCacheControlService,
        redis_connection: Redis,
        use_retry: bool = False,
        use_rate_limiter: bool = False,
        use_cache: bool = True,
        **kwargs: Any,
    ) -> None:
        self.redis_connection = redis_connection
        self.cache_service = cache_service
        self.use_retry = use_retry
        self.use_rate_limiter = use_rate_limiter
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

    async def get_data(self, wrapped_func: functools.partial, cache_key: str) -> Any:
        executor = self.build_executor(
            use_retry=self.use_retry,
            use_rate_limiter=self.use_rate_limiter,
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
                use_retry=self.use_retry,
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

    async def _update_cache(
        self,
        executor: Callable[[functools.partial], Coroutine],
        wrapped_func: functools.partial,
        cache_key: str,
    ) -> Any:
        try:
            data = await executor(wrapped_func)
        except (RateLimitException, RetryError):  # todo непонятно как тут можно убрать связанность
            return
        await self.cache_service.set_cache(redis_key=cache_key, data=data)
