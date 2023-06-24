from __future__ import annotations

import asyncio
import importlib
import sys
from concurrent.futures import wait
from functools import partial
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Coroutine,
    Literal,
    TypeVar,
    overload,
)

import anyio
from typing_extensions import ParamSpec

if TYPE_CHECKING:
    from types import ModuleType

    from anyio.abc import ObjectSendStream

    from .concurrent.futures import (
        _billiard as billiard_future,
    )
    from .concurrent.futures import (
        _multiprocessing as multiprocessing_future,
    )

__all__ = ["TimeoutExecutor", "get_executor"]

ParamT = ParamSpec("ParamT")
ResultT = TypeVar("ResultT")
IPYTHON_SHELL_NAMES = frozenset(
    {
        "ZMQInteractiveShell",
        "TerminalInteractiveShell",
    },
)


class TimeoutExecutor:
    """exec with timeout"""

    def __init__(
        self,
        timeout: float,
        context: Literal["billiard", "multiprocessing"] | None = None,
        pickler: Literal["pickle", "dill"] | None = None,
    ) -> None:
        self.timeout = timeout
        self._init = None
        self._args = ()
        self._kwargs = {}
        self._select = (context, pickler)

    def _partial_init(self) -> Callable[[], Any] | None:
        if self._init is None:
            return None
        return partial(self._init, *self._args, **self._kwargs)

    def set_init(
        self,
        init: Callable[ParamT, Any],
        *args: ParamT.args,
        **kwargs: ParamT.kwargs,
    ) -> None:
        """set init func

        Args:
            init: pickable func
        """
        self._init = init
        self._args = args
        self._kwargs = kwargs

    def apply(
        self,
        func: Callable[ParamT, ResultT],
        *args: ParamT.args,
        **kwargs: ParamT.kwargs,
    ) -> ResultT:
        """apply only pickable func

        Both args and kwargs should be pickable.

        Args:
            func: pickable func

        Raises:
            TimeoutError: When the time is exceeded
            exc: Error during pickable func execution

        Returns:
            pickable func result
        """
        executor = get_executor(self._select[0], self._select[1])
        with executor(1, initializer=self._partial_init()) as pool:
            future = pool.submit(func, *args, **kwargs)
            wait([future], timeout=self.timeout)
            if not future.done():
                pool.shutdown(wait=False)
                error_msg = f"timeout > {self.timeout}s"
                raise TimeoutError(error_msg)
            return future.result()

    async def apply_async(
        self,
        func: Callable[ParamT, Coroutine[None, None, ResultT]],
        *args: ParamT.args,
        **kwargs: ParamT.kwargs,
    ) -> ResultT:
        """apply only pickable func

        Both args and kwargs should be pickable.

        Args:
            func: pickable func

        Raises:
            TimeoutError: When the time is exceeded
            exc: Error during pickable func execution

        Returns:
            pickable func result
        """
        executor = get_executor(self._select[0], self._select[1])
        with executor(1, initializer=self._partial_init()) as pool:
            try:
                future = pool.submit(
                    _async_run,
                    func,
                    *args,
                    _timeout=self.timeout,
                    **kwargs,
                )
                coro = asyncio.wrap_future(future)
                return await coro
            except TimeoutError:
                pool.shutdown(wait=False)
                raise


@overload
def get_executor(
    context: Literal["multiprocessing"] | None = ...,
    pickler: Literal["pickle", "dill"] | None = ...,
) -> type[multiprocessing_future.ProcessPoolExecutor]:
    ...


@overload
def get_executor(
    context: Literal["billiard"] = ...,
    pickler: Literal["pickle", "dill"] | None = ...,
) -> type[billiard_future.ProcessPoolExecutor]:
    ...


def get_executor(
    context: Literal["billiard", "multiprocessing"] | None = None,
    pickler: Literal["pickle", "dill"] | None = None,
) -> (
    type[billiard_future.ProcessPoolExecutor]
    | type[multiprocessing_future.ProcessPoolExecutor]
):
    """get pool executor

    Args:
        context: billiard or multiprocessing. Defaults to None.

    Returns:
        ProcessPoolExecutor
    """
    if not context:
        context = "billiard" if _is_jupyter() and _has_billiard() else "multiprocessing"
    if not pickler:
        pickler = "dill" if _has_dill() else "pickle"

    future_module = importlib.import_module(
        f".concurrent.futures._{context}",
        __package__,
    )
    executor = future_module.ProcessPoolExecutor

    if pickler != "pickle":
        pickler_module = importlib.import_module(".pickler.dill", __package__)
        context_module: ModuleType | None = getattr(pickler_module, context, None)
        if context_module is None:
            error_msg = f"{pickler} not yet implemented"
            raise NotImplementedError(error_msg)
        context_module.monkey_patch()

    return executor


def _async_run(
    func: Callable[..., Any],
    *args: Any,
    _timeout: float,
    **kwargs: Any,
) -> Any:
    return asyncio.run(
        _async_run_with_timeout(func, *args, _timeout=_timeout, **kwargs),
    )


async def _async_run_with_timeout(
    func: Callable[..., Any],
    *args: Any,
    _timeout: float,
    **kwargs: Any,
) -> Any:
    send, recv = anyio.create_memory_object_stream()
    async with anyio.create_task_group() as task_group:
        async with anyio.fail_after(_timeout):
            async with send:
                task_group.start_soon(
                    partial(
                        _async_run_with_stream,
                        func,
                        *args,
                        _stream=send.clone(),
                        **kwargs,
                    ),
                )
            async with recv:
                result = await recv.receive()

    return result


async def _async_run_with_stream(
    func: Callable[..., Any],
    *args: Any,
    _stream: ObjectSendStream[Any],
    **kwargs: Any,
) -> None:
    async with _stream:
        result = await func(*args, **kwargs)
        await _stream.send(result)


def _is_jupyter() -> bool:
    frame = sys._getframe()  # noqa: SLF001
    while frame.f_back:
        if "get_ipython" in frame.f_globals:
            ipython_func = frame.f_globals.get("get_ipython", None)
            if callable(ipython_func):
                return _is_jupyter_from_shell(ipython_func())
        frame = frame.f_back
    if "get_ipython" in frame.f_globals:
        ipython_func = frame.f_globals.get("get_ipython", None)
        if callable(ipython_func):
            return _is_jupyter_from_shell(ipython_func())
    return False


def _is_jupyter_from_shell(shell: Any) -> bool:
    try:
        shell_name: str = type(shell).__name__
    except NameError:
        return False

    return shell_name in IPYTHON_SHELL_NAMES


def _has_dill() -> bool:
    try:
        import dill  # type: ignore # noqa: F401
    except (ImportError, ModuleNotFoundError):
        return False
    else:
        return True


def _has_billiard() -> bool:
    try:
        import billiard  # type: ignore # noqa: F401
    except (ImportError, ModuleNotFoundError):
        return False
    else:
        return True
