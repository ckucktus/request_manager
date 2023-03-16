import abc
from abc import abstractmethod
from typing import Any, Callable, List, Optional

from aioredis import Redis

from src.exceptions.exceptions import InvalidCacheError


class AbstractCacheService(abc.ABC):
    @abstractmethod
    async def get_cache(self, redis_key: str) -> Optional[str]:
        pass

    @abstractmethod
    async def set_cache(self, redis_key: str, data: Any) -> Optional[str]:
        pass


class CacheControlService(AbstractCacheService):
    def __init__(
        self,
        redis_connection: Redis,
        service_name: str,
        service_version: Optional[str] = None,
        cache_validators: List[Callable] = None,  # todo добавить версию проекта
        redis_key_factory: Callable = None,
        cache_filters: List[Callable] = None,
        **kwargs: Any,
    ) -> None:

        self.redis_connection = redis_connection
        self.cache_validators = cache_validators
        self.redis_key_factory = redis_key_factory
        self.preset_cache_filters = cache_filters
        self.service_version = service_version
        self.service_name = service_name
        self.kwargs = kwargs

    async def get_cache(self, redis_key: str) -> Optional[str]:

        result: Optional[Any] = await self.redis_connection.get(redis_key)
        if self.cache_validators and not all([validator(result) for validator in self.cache_validators]):
            raise InvalidCacheError(result)

        return result

    async def set_cache(self, redis_key: str, data: str) -> Optional[str]:
        """
        Используется для сохранения кэша
        В качестве кэша могут служить json ответов либо xml тела документов
        :param self: Access the class attributes
        :param redis_key:str: Specify the key to store the data in
        :param data:Any: Set the data in redis
        """
        if self.preset_cache_filters and not all([_filter(data) for _filter in self.preset_cache_filters]):
            raise InvalidCacheError
        result = await self.redis_connection.set(redis_key, data, **self.kwargs)
        return result
