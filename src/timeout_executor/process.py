from __future__ import annotations

import shlex
import subprocess
import sys
import tempfile
from functools import partial, wraps
from inspect import iscoroutinefunction
from os import environ
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Coroutine, Generic, overload
from uuid import uuid4

import anyio
import cloudpickle
from async_wrapper import async_to_sync, sync_to_async
from typing_extensions import ParamSpec, TypeVar, override

from timeout_executor.serde import SerializedError, dumps_error, loads_error

if TYPE_CHECKING:
    from anyio.abc import Process

__all__ = ["TimeoutExecutor", "execute_func", "delay_func"]

P = ParamSpec("P")
T = TypeVar("T", infer_variance=True)
P2 = ParamSpec("P2")
T2 = TypeVar("T2", infer_variance=True)

SENTINEL = object()
_TIMEOUT_EXECUTOR_INPUT_FILE = "_TIMEOUT_EXECUTOR_INPUT_FILE"


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
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError(exc.timeout) from exc
        finally:
            with anyio.CancelScope(shield=True):
                self._process.terminate()

    async def _delay(self, timeout: float | None) -> T:
        if self._process.returncode is not None:
            return await self._load_output()

        if timeout is None:
            timeout = self._timeout

        await wait_process(self._process, timeout, self._input)
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


class _Executor(Generic[P, T]):
    def __init__(self, timeout: float, func: Callable[P, T]) -> None:
        self._timeout = timeout
        self._func = func

    def _create_temp_files(self) -> tuple[Path, Path]:
        unique_id = uuid4()

        temp_dir = Path(tempfile.gettempdir()) / "timeout_executor"
        temp_dir.mkdir(exist_ok=True)

        unique_dir = temp_dir / str(unique_id)
        unique_dir.mkdir(exist_ok=False)

        input_file = unique_dir / "input.b"
        output_file = unique_dir / "output.b"

        return input_file, output_file

    @staticmethod
    def _command() -> list[str]:
        return shlex.split(
            f"{sys.executable} -c "
            '"from timeout_executor.process import _run_in_subprocess;_run_in_subprocess()"'
        )

    def execute(self, *args: P.args, **kwargs: P.kwargs) -> AsyncResult[T]:
        input_file, output_file = self._create_temp_files()

        input_args = (self._func, args, kwargs, output_file)
        input_args_as_bytes = cloudpickle.dumps(input_args)
        with input_file.open("wb+") as file:
            file.write(input_args_as_bytes)

        command = self._command()
        process = subprocess.Popen(
            command,  # noqa: S603
            env={_TIMEOUT_EXECUTOR_INPUT_FILE: input_file.as_posix()},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return AsyncResult(process, input_file, output_file, self._timeout)

    async def delay(self, *args: P.args, **kwargs: P.kwargs) -> AsyncResult[T]:
        input_file, output_file = self._create_temp_files()
        input_file, output_file = anyio.Path(input_file), anyio.Path(output_file)

        input_args = (self._func, args, kwargs, output_file)
        input_args_as_bytes = cloudpickle.dumps(input_args)
        async with await input_file.open("wb+") as file:
            await file.write(input_args_as_bytes)

        command = self._command()
        process = await anyio.open_process(
            command,
            env={_TIMEOUT_EXECUTOR_INPUT_FILE: input_file.as_posix()},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return AsyncResult(process, input_file, output_file, self._timeout)


@overload
def execute_func(
    timeout: float,
    func: Callable[P2, Coroutine[Any, Any, T2]],
    *args: P2.args,
    **kwargs: P2.kwargs,
) -> AsyncResult[T2]: ...


@overload
def execute_func(
    timeout: float, func: Callable[P2, T2], *args: P2.args, **kwargs: P2.kwargs
) -> AsyncResult[T2]: ...


def execute_func(
    timeout: float, func: Callable[P2, Any], *args: P2.args, **kwargs: P2.kwargs
) -> AsyncResult[Any]:
    executor = _Executor(timeout, func)
    return executor.execute(*args, **kwargs)


@overload
async def delay_func(
    timeout: float,
    func: Callable[P2, Coroutine[Any, Any, T2]],
    *args: P2.args,
    **kwargs: P2.kwargs,
) -> AsyncResult[T2]: ...


@overload
async def delay_func(
    timeout: float, func: Callable[P2, T2], *args: P2.args, **kwargs: P2.kwargs
) -> AsyncResult[T2]: ...


async def delay_func(
    timeout: float, func: Callable[P2, Any], *args: P2.args, **kwargs: P2.kwargs
) -> AsyncResult[Any]:
    executor = _Executor(timeout, func)
    return await executor.delay(*args, **kwargs)


class TimeoutExecutor(Generic[P, T]):
    execute_func = staticmethod(execute_func)
    delay_func = staticmethod(delay_func)

    if TYPE_CHECKING:

        @overload
        def __new__(
            cls, func: Callable[P, Coroutine[Any, Any, T]], timeout: float
        ) -> TimeoutExecutor[P, T]: ...
        @overload
        def __new__(
            cls, func: Callable[P, T], timeout: float
        ) -> TimeoutExecutor[P, T]: ...
        @override
        def __new__(
            cls, func: Callable[P, Any], timeout: float
        ) -> TimeoutExecutor[P, Any]: ...


def output_to_file(
    file: Path | anyio.Path,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    def wrapper(func: Callable[P, Any]) -> Callable[P, Any]:
        if iscoroutinefunction(func):
            return _output_to_file_async(file)(func)
        return _output_to_file_sync(file)(func)

    return wrapper


def _output_to_file_sync(
    file: Path | anyio.Path,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    if isinstance(file, anyio.Path):
        file = file._path  # noqa: SLF001

    def wrapper(func: Callable[P, T]) -> Callable[P, T]:
        @wraps(func)
        def inner(*args: P.args, **kwargs: P.kwargs) -> T:
            try:
                result = func(*args, **kwargs)
            except Exception as exc:
                dump = dumps_error(exc)
                raise
            else:
                dump = cloudpickle.dumps(result)
                return result
            finally:
                with file.open("wb+") as file_io:
                    file_io.write(dump)

        return inner

    return wrapper


def _output_to_file_async(
    file: Path | anyio.Path,
) -> Callable[
    [Callable[P, Coroutine[Any, Any, T]]], Callable[P, Coroutine[Any, Any, T]]
]:
    if isinstance(file, Path):
        file = anyio.Path(file)

    def wrapper(
        func: Callable[P, Coroutine[Any, Any, T]],
    ) -> Callable[P, Coroutine[Any, Any, T]]:
        @wraps(func)
        async def inner(*args: P.args, **kwargs: P.kwargs) -> T:
            try:
                result = await func(*args, **kwargs)
            except Exception as exc:
                dump = dumps_error(exc)
                raise
            else:
                dump = cloudpickle.dumps(result)
                return result
            finally:
                async with await file.open("wb+") as file_io:
                    await file_io.write(dump)

        return inner

    return wrapper


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
        with anyio.move_on_after(timeout):
            await wait_func()
    finally:
        with anyio.CancelScope(shield=True):
            if process.returncode is not None:
                await input_file.unlink(missing_ok=False)


def _run_in_subprocess() -> None:
    """only using in subprocess"""
    input_file = Path(environ.get(_TIMEOUT_EXECUTOR_INPUT_FILE, ""))
    with input_file.open("rb") as file_io:
        func, args, kwargs, output_file = cloudpickle.load(file_io)
    new_func = output_to_file(output_file)(func)

    if iscoroutinefunction(new_func):
        new_func = async_to_sync(new_func)

    new_func(*args, **kwargs)
