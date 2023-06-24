from __future__ import annotations

import asyncio
import importlib
import sys
from concurrent.futures import wait
from functools import lru_cache, partial
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

from timeout_executor.log import logger
from timeout_executor.pickler import monkey_patch, monkey_unpatch

if TYPE_CHECKING:
    from anyio.abc import ObjectSendStream

    from .concurrent.futures import _billiard as billiard_future
    from .concurrent.futures import _multiprocessing as multiprocessing_future

__all__ = ["TimeoutExecutor", "get_executor"]

ParamT = ParamSpec("ParamT")
ResultT = TypeVar("ResultT")
IPYTHON_SHELL_NAMES = frozenset(
    {
        "ZMQInteractiveShell",
        "TerminalInteractiveShell",
    },
)

ContextType = Literal["billiard", "multiprocessing"]
PicklerType = Literal["pickle", "dill", "cloudpickle"]


class TimeoutExecutor:
    """exec with timeout"""

    def __init__(
        self,
        timeout: float,
        context: ContextType | None = None,
        pickler: PicklerType | None = None,
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
                pool.shutdown(wait=False, cancel_futures=True)
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
                pool.shutdown(wait=False, cancel_futures=True)
                raise


@overload
def get_executor(
    context: Literal["multiprocessing"] | None = ...,
    pickler: PicklerType | None = ...,
) -> type[multiprocessing_future.ProcessPoolExecutor]:
    ...


@overload
def get_executor(
    context: Literal["billiard"] = ...,
    pickler: PicklerType | None = ...,
) -> type[billiard_future.ProcessPoolExecutor]:
    ...


@overload
def get_executor(
    context: str = ...,
    pickler: PicklerType | None = ...,
) -> (
    type[billiard_future.ProcessPoolExecutor]
    | type[multiprocessing_future.ProcessPoolExecutor]
):
    ...


def get_executor(
    context: ContextType | str | None = None,
    pickler: PicklerType | None = None,
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
    context, pickler = _validate_context_and_pickler(context, pickler)
    future_module = importlib.import_module(
        f".concurrent.futures._{context}",
        __package__,
    )
    executor = future_module.ProcessPoolExecutor
    _patch_or_unpatch(context, pickler)

    return executor


def _validate_context_and_pickler(
    context: Any,
    pickler: Any,
) -> tuple[ContextType, PicklerType]:
    if not context:
        context = (
            "billiard"
            if _is_jupyter() and _check_deps("billiard")
            else "multiprocessing"
        )
    if not pickler:
        if _check_deps("dill"):
            pickler = "dill"
        elif _check_deps("cloudpickle"):
            pickler = "cloudpickle"
        else:
            pickler = "pickle"

    if context == "billiard" and pickler == "pickle":
        if _check_deps("dill"):
            logger.warning("billiard will use dill")
            pickler = "dill"
        elif _check_deps("cloudpickle"):
            logger.warning("billiard will use cloudpickle")
            pickler = "cloudpickle"
        else:
            raise ModuleNotFoundError("Billiard needs dill or cloudpickle")

    return context, pickler


def _patch_or_unpatch(context: ContextType, pickler: PicklerType) -> None:
    if pickler == "pickle":
        monkey_unpatch(context)
    else:
        monkey_patch(context, pickler)


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


@lru_cache
def _check_deps(module_name: str) -> bool:
    try:
        importlib.import_module(module_name)
    except (ImportError, ModuleNotFoundError):
        return False
    else:
        return True
