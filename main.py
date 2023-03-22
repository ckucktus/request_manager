from __future__ import annotations

import inspect
from functools import partial
from typing import Any, Callable

from src.cache_invalidator_strategy.base import AbstractCacheStrategy


def build_cache_key(
    func: Callable,
    service_name: str,
    *func_call_args: Any,
    integration: str = None,
    integration_method: str = None,
    service_version: str = None,
    **func_call_kwargs: Any,
) -> str:

    static_key_sections = [service_name]
    if service_version:
        static_key_sections += [service_version]
    if integration:
        static_key_sections += [integration]
    if integration_method:
        static_key_sections += [integration_method]

    list_of_sections = static_key_sections + [
        f'{arg_name}={arg_value}'
        for arg_name, arg_value in inspect.getcallargs(func, *func_call_args, **func_call_kwargs).items()
    ]

    return ':'.join(list_of_sections)


class RequestManager:
    def __init__(
        self,
        service_name: str,
        cache_strategy: AbstractCacheStrategy,
        service_version: str = None,
        integration: str = None,
        integration_method: str = None,
        cache_key_factory: Callable = None,
    ) -> None:
        self.cache_strategy = cache_strategy
        self.cache_key_factory = cache_key_factory
        self.service_name = service_name
        self.service_version = service_version
        self.integration = integration
        self.integration_method = integration_method

    def build_cache_key(
        self,
        func: Callable,
        *func_call_args: Any,
        **func_call_kwargs: Any,
    ) -> str:
        if self.cache_key_factory:
            return self.cache_key_factory(
                func,
                self.service_name,
                self.integration,
                self.integration_method,
                *func_call_args,
                service_version=self.service_version,
                **func_call_kwargs,
            )
        return build_cache_key(
            func,
            self.service_name,
            *func_call_args,
            integration=self.integration,
            integration_method=self.integration_method,
            service_version=self.service_version,
            **func_call_kwargs,
        )

    def __call__(self, func: Callable) -> Callable:
        async def wrapped(*args: Any, **kwargs: Any) -> Any:
            cache_key = self.build_cache_key(func, *args, **kwargs)

            wrapped_func = partial(func, *args, **kwargs)

            return await self.cache_strategy.get_data(wrapped_func, cache_key=cache_key)

        return wrapped
