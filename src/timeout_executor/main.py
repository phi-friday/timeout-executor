from __future__ import annotations

from collections import deque
from contextlib import suppress
from typing import TYPE_CHECKING, Any, Callable, Generic, overload

from typing_extensions import ParamSpec, Self, TypeVar, override

from timeout_executor.executor import apply_func, delay_func
from timeout_executor.types import Callback, ProcessCallback

if TYPE_CHECKING:
    from collections.abc import Awaitable, Iterable

    from timeout_executor.result import AsyncResult

__all__ = ["TimeoutExecutor"]

P = ParamSpec("P")
T = TypeVar("T", infer_variance=True)
AnyT = TypeVar("AnyT", infer_variance=True, default=Any)


class TimeoutExecutor(Callback[Any, AnyT], Generic[AnyT]):
    """timeout executor"""

    def __init__(self, timeout: float) -> None:
        self._timeout = timeout
        self._callbacks: deque[ProcessCallback[..., AnyT]] = deque()

    @property
    def timeout(self) -> float:
        """deadline"""
        return self._timeout

    @overload
    def apply(
        self, func: Callable[P, Awaitable[T]], *args: P.args, **kwargs: P.kwargs
    ) -> AsyncResult[P, T]: ...
    @overload
    def apply(
        self, func: Callable[P, T], *args: P.args, **kwargs: P.kwargs
    ) -> AsyncResult[P, T]: ...
    def apply(
        self, func: Callable[P, Any], *args: P.args, **kwargs: P.kwargs
    ) -> AsyncResult[P, Any]:
        """run function with deadline

        Args:
            func: func(sync or async)
            *args: func args
            **kwargs: func kwargs

        Returns:
            async result container
        """
        return apply_func(self, func, *args, **kwargs)

    @overload
    async def delay(
        self, func: Callable[P, Awaitable[T]], *args: P.args, **kwargs: P.kwargs
    ) -> AsyncResult[P, T]: ...
    @overload
    async def delay(
        self, func: Callable[P, T], *args: P.args, **kwargs: P.kwargs
    ) -> AsyncResult[P, T]: ...
    async def delay(
        self, func: Callable[P, Any], *args: P.args, **kwargs: P.kwargs
    ) -> AsyncResult[P, Any]:
        """run function with deadline

        Args:
            func: func(sync or async)
            *args: func args
            **kwargs: func kwargs

        Returns:
            async result container
        """
        return await delay_func(self, func, *args, **kwargs)

    @overload
    async def apply_async(
        self, func: Callable[P, Awaitable[T]], *args: P.args, **kwargs: P.kwargs
    ) -> AsyncResult[P, T]: ...
    @overload
    async def apply_async(
        self, func: Callable[P, T], *args: P.args, **kwargs: P.kwargs
    ) -> AsyncResult[P, T]: ...
    async def apply_async(
        self, func: Callable[P, Any], *args: P.args, **kwargs: P.kwargs
    ) -> AsyncResult[P, Any]:
        """run function with deadline.

        alias of `delay`

        Args:
            func: func(sync or async)
            *args: func args
            **kwargs: func kwargs

        Returns:
            async result container
        """
        return await self.delay(func, *args, **kwargs)

    @override
    def __repr__(self) -> str:
        return f"<{type(self).__name__}, timeout: {self.timeout:.2f}s>"

    @override
    def callbacks(self) -> Iterable[ProcessCallback[..., AnyT]]:
        return self._callbacks.copy()

    @override
    def add_callback(self, callback: ProcessCallback[..., AnyT]) -> Self:
        self._callbacks.append(callback)
        return self

    @override
    def remove_callback(self, callback: ProcessCallback[..., AnyT]) -> Self:
        with suppress(ValueError):
            self._callbacks.remove(callback)
        return self
