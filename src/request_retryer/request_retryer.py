from inspect import iscoroutinefunction
from typing import Any, Callable, Optional

from tenacity import BaseRetrying, Retrying
from tenacity._asyncio import AsyncRetrying


class RequestRetryer:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.kwargs = kwargs if kwargs else {}
        self.args = args if args else []

    def __call__(self, func: Callable) -> Callable:
        if iscoroutinefunction(func):
            r: BaseRetrying = AsyncRetrying(*self.args, **self.kwargs)
        else:
            r = Retrying(*self.args, **self.kwargs)
        return r.wraps(func)
        # return wrapped
