from __future__ import annotations

import inspect
from contextvars import ContextVar
from functools import partial
from typing import Any, Callable

from src.cache_invalidator_strategy.base import AbstractCacheStrategy

USE_CACHE: ContextVar = ContextVar('USE_CACHE')
USE_CACHE.set(True)


class CacheDataUnitOfWork:
    def __init__(self, redis_connection):
        self.session = redis_connection

    def __enter__(self):
        return self


def build_cache_key(
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


class RequestManager:
    def __init__(
        self,
        service_name: str,
        service_version: str,
        cache_strategy: AbstractCacheStrategy,
        cache_key_factory = None,
    ) -> None:
        self.cache_strategy = cache_strategy
        self.cache_key_factory = cache_key_factory
        self.service_name = service_name
        self.service_version = service_version

    def build_cache_key(
        self,
        func: Callable,
        *func_call_args: Any,
        **func_call_kwargs: Any,
    ) -> str:
        if self.cache_key_factory:
            return self.cache_key_factory(func, *func_call_args, **func_call_kwargs)
        return build_cache_key(
            func,
            self.service_name,
            *func_call_args,
            service_version=self.service_version,
            **func_call_kwargs,
        )

    def __call__(self, func: Callable) -> Callable:
        async def wrapped(*args: Any, **kwargs: Any) -> Any:
            cache_key = self.build_cache_key(func, *args, **kwargs)

            wrapped_func = partial(func, *args, **kwargs)

            return await self.cache_strategy.get_data(wrapped_func, use_cache=USE_CACHE.get(), cache_key=cache_key)

        return wrapped
