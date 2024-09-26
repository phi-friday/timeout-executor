from __future__ import annotations

import shutil
import subprocess
from functools import cached_property, partial
from typing import TYPE_CHECKING, Any, Generic, Literal, overload

import anyio
import cloudpickle
from anyio.lowlevel import checkpoint
from async_wrapper import async_to_sync, sync_to_async
from typing_extensions import ParamSpec, Self, TypeVar, override

from timeout_executor.logging import logger
from timeout_executor.serde import SerializedError, loads_error
from timeout_executor.types import Callback, ProcessCallback

if TYPE_CHECKING:
    from collections.abc import Awaitable, Iterable

    from timeout_executor.terminate import Terminator
    from timeout_executor.types import ExecutorArgs


__all__ = ["AsyncResult"]

P = ParamSpec("P")
T = TypeVar("T", infer_variance=True)

SENTINEL = object()


class AsyncResult(Callback[P, T], Generic[P, T]):
    """async result container"""

    __slots__ = ("_process", "_executor_args", "_result")

    _result: Any

    def __init__(
        self, process: subprocess.Popen[str], executor_args: ExecutorArgs[P, T]
    ) -> None:
        self._process = process

        self._executor_args = executor_args
        self._result = SENTINEL

    @property
    def _func_name(self) -> str:
        return self._executor_args.func_name

    @property
    def _terminator(self) -> Terminator[P, T]:
        return self._executor_args.terminator

    @cached_property
    def _input(self) -> anyio.Path:
        return anyio.Path(self._executor_args.input_file)

    @cached_property
    def _output(self) -> anyio.Path:
        return anyio.Path(self._executor_args.output_file)

    @cached_property
    def _init(self) -> anyio.Path | None:
        return (
            None
            if self._executor_args.init_file is None
            else anyio.Path(self._executor_args.init_file)
        )

    @property
    def has_result(self) -> bool:
        """check if result is available"""
        return self._result is not SENTINEL

    @overload
    def wait(self, timeout: float | None = None) -> Awaitable[None]: ...
    @overload
    def wait(
        self, timeout: float | None = None, *, do_async: Literal[True]
    ) -> Awaitable[None]: ...
    @overload
    def wait(
        self, timeout: float | None = None, *, do_async: Literal[False]
    ) -> None: ...
    @overload
    def wait(
        self, timeout: float | None = None, *, do_async: bool = ...
    ) -> None | Awaitable[None]: ...
    def wait(
        self, timeout: float | None = None, *, do_async: bool = True
    ) -> None | Awaitable[None]:
        """wait for process to finish"""
        if timeout is None:
            timeout = self._executor_args.timeout
        if do_async:
            return self._wait(timeout)
        return async_to_sync(self._wait)(timeout)

    def result(self, timeout: float | None = None) -> T:
        """get value sync method"""
        future = async_to_sync(self.delay)
        return future(timeout)

    async def delay(self, timeout: float | None = None) -> T:
        """get value async method"""
        if timeout is None:
            timeout = self._executor_args.timeout

        try:
            return await self._delay(timeout)
        finally:
            with anyio.CancelScope(shield=True):
                self._executor_args.terminator.close("async result")
                await checkpoint()

    async def _wait(self, timeout: float) -> None:
        try:
            logger.debug("%r wait process :: deadline: %.2fs", self, timeout)
            await _wait_process(self._process, timeout, self._input)
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError(exc.timeout) from exc
        except TimeoutError as exc:
            if not exc.args:
                raise TimeoutError(timeout) from exc
            raise

    async def _delay(self, timeout: float) -> T:
        if self._process.returncode is None:
            await self.wait(timeout, do_async=True)
        return await self._load_output()

    async def _load_output(self) -> T:
        if self.has_result:
            logger.debug("%r has result.", self)
            if isinstance(self._result, SerializedError):
                self._result = loads_error(self._result)
            if isinstance(self._result, BaseException):
                raise self._result
            return self._result

        if self._process.returncode is None:
            raise RuntimeError("process is running")

        if self._executor_args.terminator.is_active:
            raise TimeoutError(self._executor_args.timeout)

        if not await self._output.exists():
            raise FileNotFoundError(self._output)

        logger.debug("%r before load output: %s", self, self._output)
        async with await self._output.open("rb") as file:
            value = await file.read()
            self._result = cloudpickle.loads(value)
        logger.debug("%r after load output :: size: %d", self, len(value))
        await _async_rmtree(self._output.parent)
        logger.debug("%r remove temp files: %s", self, self._output.parent)
        return await self._load_output()

    @override
    def __repr__(self) -> str:
        return f"<{type(self).__name__}: {self._func_name}>"

    @override
    def add_callback(self, callback: ProcessCallback[P, T]) -> Self:
        self._terminator.add_callback(callback)
        return self

    @override
    def remove_callback(self, callback: ProcessCallback[P, T]) -> Self:
        self._terminator.remove_callback(callback)
        return self

    @override
    def callbacks(self) -> Iterable[ProcessCallback[P, T]]:
        return self._terminator.callbacks()


async def _wait_process(
    process: subprocess.Popen[str], timeout: float, input_file: anyio.Path
) -> None:
    wait_func = partial(sync_to_async(process.wait), timeout)

    try:
        with anyio.fail_after(timeout):
            await wait_func()
    finally:
        with anyio.CancelScope(shield=True):
            if process.returncode is not None:
                await input_file.unlink(missing_ok=True)


_async_rmtree = sync_to_async(shutil.rmtree)
