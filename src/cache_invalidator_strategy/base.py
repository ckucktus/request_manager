from abc import ABC, abstractmethod
from contextlib import nullcontext
from typing import Any, Callable, Coroutine, Dict, Optional, TYPE_CHECKING, Type, Union

if TYPE_CHECKING:
    from src.rate_imiter.rate_limiter import SlidingWindowRateLimiter


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


class AbstractCacheStrategy(ABC):
    @abstractmethod
    async def get_data(self, wrapped_func: Callable, redis_key: str) -> Any:
        pass


class HelpUtilsMixin:
    def build_executor(
        self,
        wrapped_func: Callable[[Any, Any], Any],
        request_retryer: Optional[Callable] = None,
        rate_limiter: Optional['SlidingWindowRateLimiter'] = None,
        missed_request_retryer: Callable = dummy_decorator,
        missed_rate_limiter: Type[AsyncNullContext] = AsyncNullContext,
    ) -> Callable[[Callable, str], Coroutine]:
        """
        Вспомогательная функция фабрика, которая даст возможность запускать оборачиваемые функции в 4 кейсах:
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
        async def executor(func: Callable[[], Any], redis_key: str) -> Any:
            async with _rate_limiter(redis_key):
                return await func()

        return executor

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
