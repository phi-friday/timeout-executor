from __future__ import annotations

import subprocess
from functools import partial
from typing import TYPE_CHECKING, Any, Generic, Iterable

import anyio
import cloudpickle
from async_wrapper import async_to_sync, sync_to_async
from typing_extensions import Self, TypeVar, override

from timeout_executor.logging import logger
from timeout_executor.serde import SerializedError, loads_error
from timeout_executor.types import Callback, ProcessCallback

if TYPE_CHECKING:
    from pathlib import Path

    from timeout_executor.terminate import Terminator
    from timeout_executor.types import ExecutorArgs


__all__ = ["AsyncResult"]

T = TypeVar("T", infer_variance=True)

SENTINEL = object()


class AsyncResult(Callback, Generic[T]):
    """async result container"""

    _result: Any

    def __init__(
        self, process: subprocess.Popen[str], executor_args: ExecutorArgs
    ) -> None:
        self._process = process

        self._executor_args = executor_args
        self._result = SENTINEL

        input_file, output_file = (
            self._executor_args.input_file,
            self._executor_args.output_file,
        )

        if not isinstance(input_file, anyio.Path):
            input_file = anyio.Path(input_file)
        self._input = input_file

        if not isinstance(output_file, anyio.Path):
            output_file = anyio.Path(output_file)
        self._output = output_file

    @property
    def _func_name(self) -> str:
        return self._executor_args.func_name

    @property
    def _terminator(self) -> Terminator:
        return self._executor_args.terminator

    def result(self, timeout: float | None = None) -> T:
        """get value sync method"""
        future = async_to_sync(self.delay)
        return future(timeout)

    async def delay(self, timeout: float | None = None) -> T:
        """get value async method"""
        if timeout is None:
            timeout = self._executor_args.timeout

        try:
            logger.debug("%r wait process :: deadline: %.2fs", self, timeout)
            return await self._delay(timeout)
        finally:
            with anyio.CancelScope(shield=True):
                self._executor_args.terminator.close("async result")

    async def _delay(self, timeout: float) -> T:
        if self._process.returncode is not None:
            return await self._load_output()

        try:
            await wait_process(self._process, timeout, self._input)
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError(exc.timeout) from exc
        except TimeoutError as exc:
            if not exc.args:
                raise TimeoutError(timeout) from exc
            raise

        return await self._load_output()

    async def _load_output(self) -> T:
        if self._result is not SENTINEL:
            logger.debug("%r has result.", self)
            if isinstance(self._result, SerializedError):
                self._result = loads_error(self._result)
            if isinstance(self._result, Exception):
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

        logger.debug("%r remove temp files: %s", self, self._output.parent)
        async with anyio.create_task_group() as task_group:
            task_group.start_soon(self._output.unlink, True)  # noqa: FBT003
            task_group.start_soon(self._input.unlink, True)  # noqa: FBT003
        await self._output.parent.rmdir()
        return await self._load_output()

    def __repr__(self) -> str:
        return f"<{type(self).__name__}: {self._func_name}>"

    @override
    def add_callback(self, callback: ProcessCallback) -> Self:
        self._terminator.add_callback(callback)
        return self

    @override
    def remove_callback(self, callback: ProcessCallback) -> Self:
        self._terminator.remove_callback(callback)
        return self

    @override
    def callbacks(self) -> Iterable[ProcessCallback]:
        return self._terminator.callbacks()


async def wait_process(
    process: subprocess.Popen[str], timeout: float, input_file: Path | anyio.Path
) -> None:
    wait_func = partial(sync_to_async(process.wait), timeout)
    if not isinstance(input_file, anyio.Path):
        input_file = anyio.Path(input_file)

    try:
        with anyio.fail_after(timeout):
            await wait_func()
    finally:
        with anyio.CancelScope(shield=True):
            if process.returncode is not None:
                await input_file.unlink(missing_ok=True)
