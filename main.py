import asyncio
import inspect

import aioredis
from aioredis import ConnectionPool, Redis
from tenacity import retry, RetryError

from src.rate_imiter.rate_limiter import RateLimitException, SlidingWindowRateLimiter
from src.request_retryer.request_retryer import RequestRetryer
from typing import Any, Awaitable, Callable, Coroutine, Dict, List, Optional, Type
import pickle
from contextlib import AbstractAsyncContextManager, nullcontext


class RedisUser:
    pool: ConnectionPool = None
    connection: Redis = None

    @classmethod
    async def get_connection(cls) -> Redis:
        if not cls.pool or cls.connection:
            cls.pool = aioredis.ConnectionPool.from_url("redis://localhost:6379", decode_responses=True, db=1)
            cls.connection = Redis(connection_pool=cls.pool)

        return cls.connection


class AsyncNullContext(nullcontext):
    def __init__(self, *args, enter_result=None, **kwargs):
        super().__init__(enter_result=enter_result)

    async def __aenter__(self):
        return self.enter_result

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


def dummy_decorator(*args, **kwargs):
    def wrapper(func):
        async def decorator_fn(*args, **kwargs):
            return await func(*args, **kwargs)

        decorator_fn.retry = None

        return decorator_fn

    return wrapper


class InvalidCacheError(Exception):
    pass


class UsingCache:
    def __init__(
        self,
        service_name,
        redis_connection: Redis,
        request_retryer=retry,
        rate_limiter: Type[SlidingWindowRateLimiter] = SlidingWindowRateLimiter,
        use_cache: bool = True,
        redis_cache_key_factory: Callable = None,
        cache_filters: List[Awaitable] = None,
        cache_validators: List[Awaitable] = None,
        redis_key_factory: Callable = None,
        **kwargs,
    ):
        self.service_name = service_name
        self.rate_limiter = (
            rate_limiter(**self._build_rate_limiter_args(kwargs)) if inspect.isclass(rate_limiter) else rate_limiter
        )  # todo если сверху будут отдаваться
        self.request_retryer: Optional[Callable] = request_retryer
        self.use_cache = use_cache
        self.redis_cache_key_factory = redis_cache_key_factory
        self.redis_connection = redis_connection
        self.preset_cache_filters = cache_filters
        self.cache_validators = cache_validators
        self.redis_key_factory = redis_key_factory
        self.kwargs = kwargs

        """
        @keyword stop: tenacity
        """

    def _build_retryer_args(self, wrapped_func) -> Dict[str, Any]:
        response = {}
        if not self.kwargs:
            return response
        retryier = self.request_retryer()(wrapped_func)

        for super_class in retryier.retry.__class__.__mro__:
            response.update(dict(*inspect.signature(super_class).bind(self.kwargs).arguments.values()))

        return response

    def _build_rate_limiter_args(self, kwargs) -> Dict[str, Any]:
        response = {}
        if not self.kwargs:
            return response

        for super_class in self.rate_limiter.__mro__:
            response.update(dict(*inspect.signature(super_class).bind(self.kwargs).arguments.values()))

        return response

    def _build_executor(
        self,
        wrapped_func: Callable[[Any, Any], Any],
        request_retryer: RequestRetryer,
        rate_limiter: Type[SlidingWindowRateLimiter],
        missed_request_retryer=dummy_decorator,
        missed_rate_limiter=AsyncNullContext,
    ) -> Callable[[Callable, str, Optional[Any], Optional[Any]], Coroutine]:

        request_retryer = request_retryer if request_retryer else missed_request_retryer
        rate_limiter = rate_limiter if rate_limiter else missed_rate_limiter

        @request_retryer(**self._build_retryer_args(wrapped_func))
        async def executor(func: Callable[[Any, Any], Any], redis_key: str, *args: Any, **kwargs: Any) -> Any:
            async with rate_limiter(self.redis_connection, redis_key, **self._build_rate_limiter_args()):
                return await func(*args, **kwargs)

        return executor

    async def update_cache(self, executor, func, redis_key, *args, **kwargs):
        try:
            result = await executor(func, *args, **kwargs)
        except (RateLimitException, RetryError):
            return
        await self.set_cache(redis_key, result)

        return result

    async def get_cache(self, redis_key: str):
        result: Optional[Any] = await self.redis_connection.get(redis_key)
        if not all([validator(result) for validator in self.cache_validators]):
            raise InvalidCacheError(result)

        if isinstance(result, bytes):
            result = pickle.loads(result)
        return result

    async def set_cache(self, redis_key: str, data):
        if not all([_filter(data) for _filter in self.preset_cache_filters]):
            raise InvalidCacheError
        if not isinstance(data, str) or not isinstance(data, int):
            data = pickle.dumps(data)
        return await self.redis_connection.set(redis_key, data)

    def _build_redis_key(self, func, *func_call_args, **func_call_kwargs) -> str:
        if self.redis_key_factory:
            return self.redis_key_factory(func, *func_call_args, **func_call_kwargs)
        return "_".join(
            [self.service_name, "def", func.__qualname__]
            + [
                f"{arg_name}={arg_value.__hash__()}"
                for arg_name, arg_value in inspect.getcallargs(func, *func_call_args, **func_call_kwargs).items()
            ]
        )

    async def get_data_with_cache(self, redis_key, func: Callable[[Any, Any], Any], *args, **kwargs):
        result = None
        executor = self._build_executor(func, self.request_retryer, self.rate_limiter)

        try:
            result = await self.get_cache(redis_key)
        except InvalidCacheError:
            result = None

        if result:
            asyncio.create_task(self.update_cache(executor, func, redis_key, *args, **kwargs))
            return result

        try:
            result = await executor(func, redis_key, *args, **kwargs)
        except RateLimitException:
            executor_without_rate_limit = self._build_executor(func, self.request_retryer, AsyncNullContext)
            result = await executor_without_rate_limit(redis_key, func, *args, **kwargs)
            if result:
                asyncio.create_task(self.set_cache(redis_key, result))

        return result

    async def get_data(self, redis_key, func, *args, **kwargs):
        result = None
        executor = self._build_executor(redis_key, func, self.request_retryer, self.rate_limiter)

    def __call__(self, func):
        async def wrapped(*args, **kwargs):
            redis_key = self._build_redis_key(func, *args, **kwargs)
            if self.use_cache:
                return await self.get_data_with_cache(redis_key, func, *args, **kwargs)
            return await self.get_data(redis_key, func, *args, **kwargs)

        return wrapped


UsingCache()
