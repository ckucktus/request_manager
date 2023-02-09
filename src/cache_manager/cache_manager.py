import abc
import inspect
import pickle
from typing import Any, Callable, List, Optional

from aioredis import Redis
from tenacity import RetryError

from src.cache_invalidator_strategy.base import HelpUtilsMixin
from src.exceptions.exceptions import InvalidCacheError
from src.rate_imiter.rate_limiter import RateLimitException


class AbstractCacheService(abc.ABC):
    async def get_cache(self, redis_key: str) -> Optional[str]:
        pass

    async def set_cache(self, redis_key: str, data: Any, **kwargs) -> Optional[str]:
        pass

    def build_redis_key(
        self,
        func: Callable,
        service_name: str,
        *func_call_args: Any,
        service_version: str = None,
        **func_call_kwargs: Any,
    ) -> str:
        list_of_sections = [service_name, func.__name__] + [
            f"{arg_name}={arg_value}"
            for arg_name, arg_value in inspect.getcallargs(func, *func_call_args, **func_call_kwargs).items()
        ]
        if service_version:
            list_of_sections.insert(1, service_version)

        return ":".join(list_of_sections)


class CacheControlService(AbstractCacheService):
    def __init__(
        self,
        redis_connection: Redis,
        service_version: Optional[str] = None,
        cache_validators: List[Callable] = None,  # todo добавить версию проекта
        redis_key_factory: Callable = None,
        cache_filters: List[Callable] = None,
        **kwargs
    ):
        """
        The __init__ function is called when a class instance is created.
        It can be used to set up instance variables, which are the attributes of that class.
        The __init__ function takes an argument for each attribute and assigns it to an instance variable.

        :param self: Reference the object instance when calling class methods
        :param redis_connection:Redis: Access the redis connection
        :param service_version:Optional[str]=None: Specify the version of the service
        :param cache_validators:List[Callable]=None: Specify a list of functions that will be called to check if the cache should be used
        :param #todoдобавитьверсиюпроектаredis_key_factory:Callable=None: Generate the redis keys
        :param cache_filters:List[Callable]=None: Provide a list of functions that will be called to filter the cache key
        :param **kwargs: Дополнительные параметры для проксирования в библиотку-клиент редиса
        :return: The values of the arguments
        :doc-author: Trelent
        """
        self.redis_connection = redis_connection
        self.cache_validators = cache_validators
        self.redis_key_factory = redis_key_factory
        self.preset_cache_filters = cache_filters
        self.service_version = service_version
        self.kwargs = kwargs

    async def get_cache(self, redis_key: str) -> Optional[str]:
        """
        The get_cache function is a helper function that retrieves the cached value for a given key.
        If no cache exists, it will return None. If the cache has expired, it will delete the stale cache and return None.
        If there is an error retrieving or parsing the cached value, an InvalidCacheError will be raised.

        :param self: Access the class instance inside of a method
        :param redis_key:str: Generate the key used to store and retrieve data from redis
        :return: The result of the cache
        :doc-author: Trelent
        """
        result: Optional[Any] = await self.redis_connection.get(redis_key)
        if self.cache_validators and not all([validator(result) for validator in self.cache_validators]):
            raise InvalidCacheError(result)

        # if isinstance(result, bytes):
        #     result = pickle.loads(result)  # todo можно выпилить если трогать будем клиент httpx
        return result

    async def set_cache(self, redis_key: str, data: str, **kwargs: Any) -> Optional[str]:
        """
        Используется для сохранения кэша
        В качестве кэша могут служить json ответов либо xml тела документов
        :param self: Access the class attributes
        :param redis_key:str: Specify the key to store the data in
        :param data:Any: Set the data in redis
        """
        if self.preset_cache_filters and not all([_filter(data) for _filter in self.preset_cache_filters]):
            raise InvalidCacheError
        return await self.redis_connection.set(redis_key, data, **kwargs)

    def build_redis_key(
        self,
        func: Callable,
        service_name: str,
        *func_call_args: Any,
        service_version: str = None,
        **func_call_kwargs: Any,
    ) -> str:
        if self.redis_key_factory:
            return self.redis_key_factory(func, *func_call_args, **func_call_kwargs)
        return super().build_redis_key(
            func,
            service_name,
            *func_call_args,
            service_version=service_version,
            **func_call_kwargs,
        )
