from __future__ import annotations

import subprocess
from functools import partial
from typing import TYPE_CHECKING, Any, Generic

import anyio
import cloudpickle
from async_wrapper import async_to_sync, sync_to_async
from typing_extensions import TypeVar

from timeout_executor.serde import SerializedError, loads_error

if TYPE_CHECKING:
    from pathlib import Path

    from anyio.abc import Process

__all__ = ["AsyncResult"]

T = TypeVar("T", infer_variance=True)

SENTINEL = object()


class AsyncResult(Generic[T]):
    _result: Any

    def __init__(
        self,
        process: subprocess.Popen | Process,
        input_file: Path | anyio.Path,
        output_file: Path | anyio.Path,
        timeout: float,
    ) -> None:
        self._process = process
        self._timeout = timeout
        self._result = SENTINEL

        if not isinstance(output_file, anyio.Path):
            output_file = anyio.Path(output_file)
        self._output = output_file

        if not isinstance(input_file, anyio.Path):
            input_file = anyio.Path(input_file)
        self._input = input_file

    def result(self, timeout: float | None = None) -> T:
        future = async_to_sync(self.delay)
        return future(timeout)

    async def delay(self, timeout: float | None = None) -> T:
        try:
            return await self._delay(timeout)
        finally:
            with anyio.CancelScope(shield=True):
                self._process.terminate()

    async def _delay(self, timeout: float | None) -> T:
        if self._process.returncode is not None:
            return await self._load_output()

        if timeout is None:
            timeout = self._timeout

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
            if isinstance(self._result, SerializedError):
                self._result = loads_error(self._result)
            if isinstance(self._result, Exception):
                raise self._result
            return self._result

        if self._process.returncode is None:
            raise RuntimeError("process is running")

        if not await self._output.exists():
            raise FileNotFoundError(self._output)

        async with await self._output.open("rb") as file:
            value = await file.read()
            self._result = cloudpickle.loads(value)

        return await self._load_output()


async def wait_process(
    process: subprocess.Popen | Process, timeout: float, input_file: Path | anyio.Path
) -> None:
    if isinstance(process, subprocess.Popen):
        wait_func = partial(sync_to_async(process.wait), timeout)
    else:
        wait_func = process.wait

    if not isinstance(input_file, anyio.Path):
        input_file = anyio.Path(input_file)

    try:
        with anyio.fail_after(timeout):
            await wait_func()
    finally:
        with anyio.CancelScope(shield=True):
            if process.returncode is not None:
                await input_file.unlink(missing_ok=False)
