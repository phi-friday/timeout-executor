from __future__ import annotations

from collections import deque
from contextlib import suppress
from typing import TYPE_CHECKING, Any, Callable, Coroutine, Iterable, overload

from typing_extensions import ParamSpec, Self, TypeVar, override

from timeout_executor.executor import apply_func, delay_func
from timeout_executor.types import Callback, ProcessCallback

if TYPE_CHECKING:
    from timeout_executor.result import AsyncResult

__all__ = ["TimeoutExecutor"]

P = ParamSpec("P")
T = TypeVar("T", infer_variance=True)


class TimeoutExecutor(Callback):
    """timeout executor"""

    def __init__(self, timeout: float) -> None:
        self._timeout = timeout
        self._callbacks: deque[ProcessCallback] = deque()

    @property
    def timeout(self) -> float:
        """deadline"""
        return self._timeout

    @overload
    def apply(
        self,
        func: Callable[P, Coroutine[Any, Any, T]],
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> AsyncResult[T]: ...
    @overload
    def apply(
        self, func: Callable[P, T], *args: P.args, **kwargs: P.kwargs
    ) -> AsyncResult[T]: ...
    def apply(
        self, func: Callable[P, Any], *args: P.args, **kwargs: P.kwargs
    ) -> AsyncResult[Any]:
        """run function with deadline

        Args:
            func: func(sync or async)

        Returns:
            async result container
        """
        return apply_func(self, func, *args, **kwargs)

    @overload
    async def delay(
        self,
        func: Callable[P, Coroutine[Any, Any, T]],
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> AsyncResult[T]: ...
    @overload
    async def delay(
        self, func: Callable[P, T], *args: P.args, **kwargs: P.kwargs
    ) -> AsyncResult[T]: ...
    async def delay(
        self, func: Callable[P, Any], *args: P.args, **kwargs: P.kwargs
    ) -> AsyncResult[Any]:
        """run function with deadline

        Args:
            func: func(sync or async)

        Returns:
            async result container
        """
        return await delay_func(self, func, *args, **kwargs)

    @overload
    async def apply_async(
        self,
        func: Callable[P, Coroutine[Any, Any, T]],
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> AsyncResult[T]: ...
    @overload
    async def apply_async(
        self, func: Callable[P, T], *args: P.args, **kwargs: P.kwargs
    ) -> AsyncResult[T]: ...
    async def apply_async(
        self, func: Callable[P, Any], *args: P.args, **kwargs: P.kwargs
    ) -> AsyncResult[Any]:
        """run function with deadline.

        alias of `delay`

        Args:
            func: func(sync or async)

        Returns:
            async result container
        """
        return await self.delay(func, *args, **kwargs)

    def __repr__(self) -> str:
        return f"<{type(self).__name__}, timeout: {self.timeout:.2f}s>"

    @override
    def callbacks(self) -> Iterable[ProcessCallback]:
        return self._callbacks.copy()

    @override
    def add_callback(self, callback: ProcessCallback) -> Self:
        self._callbacks.append(callback)
        return self

    @override
    def remove_callback(self, callback: ProcessCallback) -> Self:
        with suppress(ValueError):
            self._callbacks.remove(callback)
        return self
