import asyncio
import inspect

import aioredis
from aioredis import ConnectionPool, Redis
from tenacity import RetryError

from src.rate_imiter.rate_limiter import RateLimitException, SlidingWindowRateLimiter
from typing import Any, Callable, Coroutine, Dict, List, Optional, Type, Union
import pickle
from contextlib import nullcontext


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
    def __init__(self, *args: Any, enter_result: Any = None, **kwargs: Any) -> None:
        super().__init__(enter_result=enter_result)

    async def __aenter__(self) -> Any:
        return self.enter_result

    async def __aexit__(self, *exc: Any) -> None:
        pass


def dummy_decorator(*args: Any, **kwargs: Any) -> Callable:
    def wrapper(func: Callable) -> Callable:
        async def decorator_fn(*args: Any, **kwargs: Any):
            return await func(*args, **kwargs)

        decorator_fn.retry = None

        return decorator_fn

    return wrapper


class InvalidCacheError(Exception):
    pass


class RequestManager:
    def __init__(
        self,
        service_name: str,
        redis_connection: Redis,
        request_retryer: Optional[Callable] = None,
        rate_limiter: SlidingWindowRateLimiter = None,
        use_cache: bool = True,
        cache_filters: List[Callable] = None,
        cache_validators: List[Callable] = None,
        redis_key_factory: Callable = None,
        **kwargs: Any,
    ) -> None:
        self.service_name = service_name
        self.rate_limiter = rate_limiter
        self.request_retryer = request_retryer
        self.use_cache = use_cache
        self.redis_connection = redis_connection
        self.preset_cache_filters = cache_filters
        self.cache_validators = cache_validators
        self.redis_key_factory = redis_key_factory
        self.kwargs = kwargs

    def _build_retryer_args(self, wrapped_func: Callable[[Any, Any], Any]) -> Dict[str, Any]:

        """
        Итерируется по родительским классам и если находит соответствие имен между конструктором родительского класса
        и кваргами то, записывает это в аргументы для построения инстанса ретраера
        """

        response: Dict[str, Any] = {}
        if not self.kwargs or not self.request_retryer:
            return response
        retryer = self.request_retryer()(wrapped_func)

        for super_class in retryer.retry.__class__.__mro__:
            response.update(dict(*inspect.signature(super_class).bind(self.kwargs).arguments.values()))

        return response

    def _build_rate_limiter_args(self) -> Dict[str, Any]:

        """
        Итерируется по родительским классам и если находит соответствие имен между конструктором родительского класса
        и кваргами то, записывает это в аргументы для построения инстанса огранечителя запросов
        """

        response: Dict[str, Any] = {}
        if not self.kwargs:
            return response

        for super_class in self.rate_limiter.__class__.__mro__:
            response.update(dict(*inspect.signature(super_class).bind(self.kwargs).arguments.values()))

        return response

    def _build_executor(
        self,
        wrapped_func: Callable[[Any, Any], Any],
        request_retryer: Optional[Callable] = None,
        rate_limiter: Optional[SlidingWindowRateLimiter] = None,
        missed_request_retryer: Callable = dummy_decorator,
        missed_rate_limiter: Type[AsyncNullContext] = AsyncNullContext,
    ) -> Callable[[Callable, str, Optional[Any], Optional[Any]], Coroutine]:
        """
        Вспомогательная функция фабрика, которая даст даст запускать оборачиваемые функции в 4 кейсах:
        1) Запуск с лимитом запросов в n-ый промежуток времени и с ретраями
        2) Запуск без лимитов, но с ретраями
        3) Запуск с лимитами, но без ретраев
        4) Оставит всё, как есть
        """

        request_retryer = request_retryer if request_retryer else missed_request_retryer
        _rate_limiter: Union[SlidingWindowRateLimiter, Type[AsyncNullContext]] = (
            rate_limiter if rate_limiter else missed_rate_limiter
        )

        retryer_args = self._build_retryer_args(wrapped_func)

        @request_retryer(**retryer_args)
        async def executor(func: Callable[[Any, Any], Any], redis_key: str, *args: Any, **kwargs: Any) -> Any:
            async with _rate_limiter(redis_key):
                return await func(*args, **kwargs)

        return executor

    async def update_cache(self, executor: Callable, func: Callable, redis_key: str, *args: Any, **kwargs: Any) -> Any:
        """Обновляет кэш фоновым процессом"""
        try:
            result = await executor(func, *args, **kwargs)
        except (RateLimitException, RetryError):
            return
        await self.set_cache(redis_key, result)

        return result

    async def get_cache(self, redis_key: str) -> Any:
        result: Optional[Any] = await self.redis_connection.get(redis_key)
        if self.cache_validators and not all([validator(result) for validator in self.cache_validators]):
            raise InvalidCacheError(result)

        if isinstance(result, bytes):
            result = pickle.loads(result)
        return result

    async def set_cache(self, redis_key: str, data: Any) -> Optional[str]:
        if self.preset_cache_filters and not all([_filter(data) for _filter in self.preset_cache_filters]):
            raise InvalidCacheError
        if not isinstance(data, str) or not isinstance(data, int):
            data = pickle.dumps(data)
        return await self.redis_connection.set(redis_key, data)

    def _build_redis_key(self, func: Callable, *func_call_args: Any, **func_call_kwargs: Any) -> str:
        if self.redis_key_factory:
            return self.redis_key_factory(func, *func_call_args, **func_call_kwargs)
        return "_".join(
            [self.service_name, "def", func.__qualname__]
            + [
                f"{arg_name}={arg_value}"
                for arg_name, arg_value in inspect.getcallargs(func, *func_call_args, **func_call_kwargs).items()
            ]
        )  # todo читаемость или память

    async def get_data_with_cache(self, redis_key, func: Callable[[Any, Any], Any], *args, **kwargs) -> Any:
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
            executor_without_rate_limit = self._build_executor(
                func, request_retryer=self.request_retryer, rate_limiter=None
            )
            result = await executor_without_rate_limit(func, redis_key, *args, **kwargs)
            if result:
                asyncio.create_task(self.set_cache(redis_key, result))

        return result

    async def get_data(self, redis_key: str, func: Callable, *args: Any, **kwargs: Any) -> Any:
        raise NotImplemented

    def __call__(self, func: Callable) -> Callable:
        async def wrapped(*args: Any, **kwargs: Any) -> Any:
            redis_key = self._build_redis_key(func, *args, **kwargs)
            if self.use_cache:
                return await self.get_data_with_cache(redis_key, func, *args, **kwargs)
            return await self.get_data(redis_key, func, *args, **kwargs)

        return wrapped
