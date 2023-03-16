import functools
import inspect
from abc import ABC, abstractmethod
from contextlib import nullcontext
from functools import partial
from typing import TYPE_CHECKING, Any, Callable, Coroutine, Dict, Optional, Type, Union

if TYPE_CHECKING:
    from src.rate_imiter.rate_limiter import SlidingWindowRateLimiter

from aioredis import Redis
from tenacity import AsyncRetrying


class AsyncNullContext(nullcontext):
    def __init__(self, *args: Any, enter_result: Any = None, **kwargs: Any) -> None:
        super().__init__(enter_result=enter_result)

    async def __aenter__(self) -> Any:
        return self.enter_result

    async def __aexit__(self, *exc: Any) -> None:
        pass


def dummy_decorator(*args: Any, **kwargs: Any) -> Callable:
    def decorator(func):
        return func

    return decorator


class AbstractCacheStrategy(ABC):
    @abstractmethod
    async def get_data(
        self,
        wrapped_func: partial,
        cache_key: str,
        use_cache: bool = True,  # для тестирования
    ) -> Any:
        pass


class HelpUtilsMixin:
    def build_executor(
        self,
        redis_connection: Redis,
        cache_key: str,
        request_retryer: Optional[Callable],
        rate_limiter: Optional[Type['SlidingWindowRateLimiter']],
        **kwargs: Any,
    ) -> Callable[[functools.partial], Coroutine]:
        """
        Вспомогательная функция фабрика, которая даст возможность запускать оборачиваемые функции в 4 кейсах:
        1) Запуск с лимитом запросов в n-ый промежуток времени и с ретраями
        2) Запуск без лимитов, но с ретраями
        3) Запуск с лимитами, но без ретраев
        4) Оставит всё, как есть
        """

        request_retryer = request_retryer if request_retryer else dummy_decorator
        _rate_limiter: Union[Type[SlidingWindowRateLimiter], Callable] = (
            rate_limiter if rate_limiter else dummy_decorator
        )

        retryer_args = self._build_retryer_args(**kwargs)

        @request_retryer(**retryer_args)
        @_rate_limiter(cache_key=cache_key, redis_connection=redis_connection)
        async def executor(func: functools.partial) -> Any:
            # async with _rate_limiter(cache_key):
            return await func()

        return executor

    def _build_retryer_args(self, **kwargs) -> Dict[str, Any]:

        """
        Итерируется по родительским классам и если находит соответствие имен между конструктором родительского класса
        и кваргами то, записывает это в аргументы для построения инстанса ретраера
        """

        response: Dict[str, Any] = {}
        if not kwargs:
            return response

        for super_class in AsyncRetrying.__mro__:
            response.update(dict(*inspect.signature(super_class).bind(kwargs).arguments.values()))

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
