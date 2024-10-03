from __future__ import annotations

from collections import deque
from contextlib import suppress
from importlib.util import find_spec
from typing import TYPE_CHECKING, Any, Callable, Generic, overload

from typing_extensions import ParamSpec, Self, TypeVar, override

from timeout_executor.executor import apply_func, delay_func
from timeout_executor.types import Callback, InitializerArgs, ProcessCallback

if TYPE_CHECKING:
    from collections.abc import Awaitable, Iterable

    from timeout_executor.result import AsyncResult

__all__ = ["TimeoutExecutor"]

P = ParamSpec("P")
T = TypeVar("T", infer_variance=True)
AnyT = TypeVar("AnyT", infer_variance=True, default=Any)


class TimeoutExecutor(Callback[Any, AnyT], Generic[AnyT]):
    """timeout executor"""

    __slots__ = ("_timeout", "_callbacks", "initializer", "_use_jinja")

    def __init__(self, timeout: float, *, use_jinja: bool = False) -> None:
        self._timeout = timeout
        self._callbacks: deque[ProcessCallback[..., AnyT]] = deque()
        self.initializer: InitializerArgs[..., Any] | None = None
        self.use_jinja = use_jinja

    @property
    def timeout(self) -> float:
        """deadline"""
        return self._timeout

    @property
    def use_jinja(self) -> bool:
        """use jinja"""
        return self._use_jinja

    @use_jinja.setter
    def use_jinja(self, value: bool) -> None:
        self._use_jinja = value
        if value:
            spec = find_spec("jinja2")
            if spec is None:  # pragma: no cover
                error_msg = (
                    "Please install the dependencies "
                    "by running 'pip install timeout_executor[jinja]'."
                )
                raise ImportError(error_msg)

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
    ) -> AsyncResult[P, Any]:  # pragma: no cover
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

    def set_initializer(
        self, initializer: Callable[P, Any], *args: P.args, **kwargs: P.kwargs
    ) -> Self:
        """set initializer

        Args:
            initializer: initializer function
            *args: initializer args
            **kwargs: initializer kwargs

        Returns:
            self
        """
        self.initializer = InitializerArgs(
            function=initializer, args=args, kwargs=kwargs
        )
        return self

    def unset_initializer(self) -> Self:
        """unset initializer

        to use chain method

        Returns:
            self
        """
        self.initializer = None
        return self
