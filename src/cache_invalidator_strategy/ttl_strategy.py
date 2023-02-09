from typing import Any, Callable, Optional

from .base import AbstractCacheStrategy, HelpUtilsMixin
from ..cache_manager.cache_manager import AbstractCacheService


class TTLInvalidator(AbstractCacheStrategy, HelpUtilsMixin):
    def __init__(
        self,
        cache_service: AbstractCacheService,
        request_retryer: Optional[Callable] = None,
        use_cache: bool = True,  # TODO пересмотреть целесообразность этого параметра, все же стоит сделать кэширование обязательным, если нужны ретраи и ограничитель можно будет использовать их по отдельности
        **kwargs: Any,
    ) -> None:
        self.request_retryer = request_retryer
        self.use_cache = use_cache
        self.cache_service = cache_service
        self.kwargs = kwargs

    async def get_data(
        self,
        wrapped_func: Callable,
        redis_key: str,
        **kwargs, # todo передавать аргументы в конструктор кэш контроллера
    ) -> Any:
        executor = self.build_executor(wrapped_func, self.request_retryer)

        cache = self.cache_service.get_cache(redis_key)
        if cache:
            return cache
        result = await executor(wrapped_func, redis_key)
        if result:
            await self.cache_service.set_cache(redis_key, result, **kwargs)

        return result
