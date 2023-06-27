from __future__ import annotations

import asyncio
from concurrent.futures import wait
from functools import partial
from typing import TYPE_CHECKING, Any, Callable, Coroutine, Literal, TypeVar, overload

import anyio
from typing_extensions import ParamSpec

from timeout_executor.concurrent import get_executor_backend
from timeout_executor.pickler import monkey_patch
from timeout_executor.pickler.lock import patch_lock

if TYPE_CHECKING:
    from threading import RLock

    from anyio.abc import ObjectSendStream

    from timeout_executor.concurrent.futures.backend import _billiard as billiard_future
    from timeout_executor.concurrent.futures.backend import _loky as loky_future
    from timeout_executor.concurrent.futures.backend import (
        _multiprocessing as multiprocessing_future,
    )
    from timeout_executor.concurrent.main import BackendType
    from timeout_executor.pickler.main import PicklerType

__all__ = ["TimeoutExecutor", "get_executor"]

ParamT = ParamSpec("ParamT")
ResultT = TypeVar("ResultT")


class TimeoutExecutor:
    """exec with timeout"""

    def __init__(
        self,
        timeout: float,
        backend: BackendType | None = None,
        pickler: PicklerType | None = None,
    ) -> None:
        self.timeout = timeout
        self._init = None
        self._args = ()
        self._kwargs = {}
        self._select = (backend, pickler)

    @property
    def lock(self) -> RLock:
        """patch lock"""

        return patch_lock

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
                pool.shutdown(False, True)  # noqa: FBT003
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
                pool.shutdown(False, True)  # noqa: FBT003
                raise


@overload
def get_executor(
    backend: Literal["multiprocessing"] | None = ...,
    pickler: PicklerType | None = ...,
) -> type[multiprocessing_future.ProcessPoolExecutor]:
    ...


@overload
def get_executor(
    backend: Literal["billiard"] = ...,
    pickler: PicklerType | None = ...,
) -> type[billiard_future.ProcessPoolExecutor]:
    ...


@overload
def get_executor(
    backend: Literal["loky"] = ...,
    pickler: PicklerType | None = ...,
) -> type[loky_future.ProcessPoolExecutor]:
    ...


def get_executor(
    backend: BackendType | None = None,
    pickler: PicklerType | None = None,
) -> (
    type[billiard_future.ProcessPoolExecutor]
    | type[multiprocessing_future.ProcessPoolExecutor]
    | type[loky_future.ProcessPoolExecutor]
):
    """get pool executor

    Args:
        backend: billiard or multiprocessing. Defaults to None.

    Returns:
        ProcessPoolExecutor
    """
    backend = backend or "multiprocessing"
    executor = get_executor_backend(backend)
    monkey_patch(backend, pickler)
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
