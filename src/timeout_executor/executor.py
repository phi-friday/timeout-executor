from __future__ import annotations

import shlex
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Coroutine, Generic, overload
from uuid import uuid4

import anyio
import cloudpickle
from typing_extensions import ParamSpec, TypeVar

from timeout_executor.const import SUBPROCESS_COMMAND, TIMEOUT_EXECUTOR_INPUT_FILE
from timeout_executor.result import AsyncResult
from timeout_executor.terminate import Terminator

__all__ = ["apply_func", "delay_func"]

P = ParamSpec("P")
T = TypeVar("T", infer_variance=True)
P2 = ParamSpec("P2")
T2 = TypeVar("T2", infer_variance=True)


class Executor(Generic[P, T]):
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
        return shlex.split(f'{sys.executable} -c "{SUBPROCESS_COMMAND}"')

    def apply(self, *args: P.args, **kwargs: P.kwargs) -> AsyncResult[T]:
        input_file, output_file = self._create_temp_files()

        input_args = (self._func, args, kwargs, output_file)
        input_args_as_bytes = cloudpickle.dumps(input_args)
        with input_file.open("wb+") as file:
            file.write(input_args_as_bytes)

        command = self._command()
        terminator = Terminator(self._timeout)
        process = subprocess.Popen(
            command,  # noqa: S603
            env={TIMEOUT_EXECUTOR_INPUT_FILE: input_file.as_posix()},
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        terminator.process = process
        return AsyncResult(process, terminator, input_file, output_file, self._timeout)

    async def delay(self, *args: P.args, **kwargs: P.kwargs) -> AsyncResult[T]:
        input_file, output_file = self._create_temp_files()
        input_file, output_file = anyio.Path(input_file), anyio.Path(output_file)

        input_args = (self._func, args, kwargs, output_file)
        input_args_as_bytes = cloudpickle.dumps(input_args)
        async with await input_file.open("wb+") as file:
            await file.write(input_args_as_bytes)

        command = self._command()
        terminator = Terminator(self._timeout)
        process = subprocess.Popen(  # noqa: ASYNC101
            command,  # noqa: S603
            env={TIMEOUT_EXECUTOR_INPUT_FILE: input_file.as_posix()},
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        terminator.process = process
        return AsyncResult(process, terminator, input_file, output_file, self._timeout)


@overload
def apply_func(
    timeout: float,
    func: Callable[P2, Coroutine[Any, Any, T2]],
    *args: P2.args,
    **kwargs: P2.kwargs,
) -> AsyncResult[T2]: ...


@overload
def apply_func(
    timeout: float, func: Callable[P2, T2], *args: P2.args, **kwargs: P2.kwargs
) -> AsyncResult[T2]: ...


def apply_func(
    timeout: float, func: Callable[P2, Any], *args: P2.args, **kwargs: P2.kwargs
) -> AsyncResult[Any]:
    """run function with deadline

    Args:
        timeout: deadline
        func: func(sync or async)

    Returns:
        async result container
    """
    executor = Executor(timeout, func)
    return executor.apply(*args, **kwargs)


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
    """run function with deadline

    Args:
        timeout: deadline
        func: func(sync or async)

    Returns:
        async result container
    """
    executor = Executor(timeout, func)
    return await executor.delay(*args, **kwargs)
