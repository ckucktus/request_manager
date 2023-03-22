import functools
import inspect
from abc import ABC, abstractmethod
from functools import partial
from typing import Any, Callable, Coroutine, Dict, Type, Union

from tenacity import AsyncRetrying, retry

from src.rate_imiter.rate_limiter import SlidingWindowRateLimiter


def dummy_decorator(*args: Any, **kwargs: Any) -> Callable:
    def decorator(func: Callable) -> Any:
        return func

    return decorator


class AbstractCacheStrategy(ABC):
    @abstractmethod
    async def get_data(
        self,
        wrapped_func: partial,
        cache_key: str,
    ) -> Any:
        pass


class HelpUtilsMixin:
    def build_executor(
        self,
        use_retry: bool,
        use_rate_limiter: bool,
        **kwargs: Any,
    ) -> Callable[[functools.partial], Coroutine]:
        """
        Вспомогательная функция фабрика, которая даст возможность запускать оборачиваемые функции в 4 кейсах:
        1) Запуск с лимитом запросов в n-ый промежуток времени и с ретраями
        2) Запуск без лимитов, но с ретраями
        3) Запуск с лимитами, но без ретраев
        4) Оставит всё, как есть


        :param use_retry:
        :param use_rate_limiter:

        Параметры для ретрая
        :param sleep:
        :param stop:
        :param wait:
        :param retry:
        :param before:
        :param after:
        :param before_sleep:
        :param reraise:
        :param retry_error_cls:
        :param retry_error_callback:

        Параметры для ограничителя запросов
        :param cache_key:
        :param rate_for_second:
        :param rate_for_minute:
        :param rate_for_hour:
        :param rate_for_day:
        :param redis_connection
        """

        request_retryer: Callable = retry if use_retry else dummy_decorator  # type: ignore
        rate_limiter: Union[Type[SlidingWindowRateLimiter], Callable] = (
            SlidingWindowRateLimiter if use_rate_limiter else dummy_decorator
        )

        retryer_args = self._build_init_args(_class=AsyncRetrying, **kwargs) if use_rate_limiter else {}
        rate_limiter_args = self._build_init_args(_class=SlidingWindowRateLimiter, **kwargs) if use_rate_limiter else {}

        @request_retryer(**retryer_args)
        @rate_limiter(**rate_limiter_args)
        async def executor(func: functools.partial) -> Any:
            return await func()

        return executor

    @staticmethod
    def _build_init_args(
        _class: Union[Type['SlidingWindowRateLimiter'], Type[AsyncRetrying]], **kwargs: Any
    ) -> Dict[str, Any]:
        """
        Итерируется по родительским классам и если находит соответствие имен между конструктором родительского класса
        и кваргами то, записывает это в аргументы для построения инстанса
        """

        response: Dict[str, Any] = {}
        if not kwargs:
            return response

        for super_class in _class.__mro__[1::-1]:
            signature = inspect.signature(super_class)
            if intersection := (signature.parameters.keys() & kwargs.keys()):
                response.update({i: kwargs[i] for i in intersection})

        return response
