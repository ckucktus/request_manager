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


class BaseCacheControlService(AbstractCacheService):
    def __init__(
        self,
        redis_connection: Redis,
        **kwargs: Any,
    ) -> None:
        """

        :param ex: Set the specified expire time, in seconds,
        :param px: Set the specified expire time, in milliseconds,
        :param nx: Only set the key if it does not already exist,
        :param xx: Only set the key if it already exist,
        :param keepttl: Retain the time to live associated with the key,
        """
        self.redis_connection = redis_connection
        self.kwargs = kwargs

    async def get_cache(self, redis_key: str) -> Optional[str]:
        return await self.redis_connection.get(redis_key)

    async def set_cache(self, redis_key: str, data: Any) -> Optional[str]:
        return await self.redis_connection.set(redis_key, data, **self.kwargs)


class CacheControlService(BaseCacheControlService):
    def __init__(
        self,
        redis_connection: Redis,
        cache_validators: Optional[List[Callable]] = None,
        cache_filters: Optional[List[Callable]] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(redis_connection=redis_connection, **kwargs)
        self.cache_validators = cache_validators
        self.preset_cache_filters = cache_filters
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
        """
        if self.preset_cache_filters and not all([_filter(data) for _filter in self.preset_cache_filters]):
            raise InvalidCacheError
        return await self.redis_connection.set(redis_key, data, **self.kwargs)
