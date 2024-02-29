from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Coroutine, overload

from typing_extensions import ParamSpec, TypeVar

from timeout_executor.executor import Executor, apply_func, delay_func

if TYPE_CHECKING:
    from timeout_executor.result import AsyncResult

__all__ = ["TimeoutExecutor"]

P = ParamSpec("P")
T = TypeVar("T", infer_variance=True)


class TimeoutExecutor:
    """timeout executor"""

    def __init__(self, timeout: float) -> None:
        self._timeout = timeout

    def _create_executor(self, func: Callable[P, T]) -> Executor[P, T]:
        return Executor(self._timeout, func)

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
        return apply_func(self._timeout, func, *args, **kwargs)

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
        return await delay_func(self._timeout, func, *args, **kwargs)

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
