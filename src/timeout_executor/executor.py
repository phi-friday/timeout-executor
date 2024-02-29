from __future__ import annotations

import shlex
import subprocess
import sys
import tempfile
from inspect import isclass
from pathlib import Path
from types import FunctionType
from typing import Any, Callable, Coroutine, Generic, overload
from uuid import uuid4

import anyio
import cloudpickle
from typing_extensions import ParamSpec, TypeVar

from timeout_executor.const import SUBPROCESS_COMMAND, TIMEOUT_EXECUTOR_INPUT_FILE
from timeout_executor.logging import logger
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
        self._func_name = func_name(func)
        self._unique_id = uuid4()

    def _create_temp_files(self) -> tuple[Path, Path]:
        temp_dir = Path(tempfile.gettempdir()) / "timeout_executor"
        temp_dir.mkdir(exist_ok=True)

        unique_dir = temp_dir / str(self._unique_id)
        unique_dir.mkdir(exist_ok=False)

        input_file = unique_dir / "input.b"
        output_file = unique_dir / "output.b"

        return input_file, output_file

    def _command(self, stacklevel: int = 2) -> list[str]:
        command = f'{sys.executable} -c "{SUBPROCESS_COMMAND}"'
        logger.debug("%r command: %s", self, command, stacklevel=stacklevel)
        return shlex.split(command)

    def _dump_args(
        self, output_file: Path | anyio.Path, *args: P.args, **kwargs: P.kwargs
    ) -> bytes:
        input_args = (self._func, args, kwargs, output_file)
        logger.debug("%r before dump input args", self)
        input_args_as_bytes = cloudpickle.dumps(input_args)
        logger.debug(
            "%r after dump input args :: size: %d", self, len(input_args_as_bytes)
        )
        return input_args_as_bytes

    def _create_process(self, input_file: Path | anyio.Path) -> subprocess.Popen[str]:
        command = self._command(stacklevel=3)
        logger.debug("%r before create new process", self)
        process = subprocess.Popen(
            command,  # noqa: S603
            env={TIMEOUT_EXECUTOR_INPUT_FILE: input_file.as_posix()},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        logger.debug("%r process: %d", self, process.pid)
        return process

    def apply(self, *args: P.args, **kwargs: P.kwargs) -> AsyncResult[T]:
        input_file, output_file = self._create_temp_files()
        input_args_as_bytes = self._dump_args(output_file, *args, **kwargs)

        logger.debug("%r before write input file", self)
        with input_file.open("wb+") as file:
            file.write(input_args_as_bytes)
        logger.debug("%r after write input file", self)

        terminator = Terminator(self._timeout, self._func_name)
        process = self._create_process(input_file)
        terminator.process = process
        return AsyncResult(process, terminator, input_file, output_file, self._timeout)

    async def delay(self, *args: P.args, **kwargs: P.kwargs) -> AsyncResult[T]:
        input_file, output_file = self._create_temp_files()
        input_file, output_file = anyio.Path(input_file), anyio.Path(output_file)
        input_args_as_bytes = self._dump_args(output_file, *args, **kwargs)

        logger.debug("%r before write input file", self)
        async with await input_file.open("wb+") as file:
            await file.write(input_args_as_bytes)
        logger.debug("%r after write input file", self)

        terminator = Terminator(self._timeout, self._func_name)
        process = self._create_process(input_file)
        terminator.process = process
        return AsyncResult(process, terminator, input_file, output_file, self._timeout)

    def __repr__(self) -> str:
        return f"<{type(self).__name__}: {self._func_name}>"


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


def func_name(func: Callable[..., Any]) -> str:
    if isinstance(func, FunctionType) or isclass(func):
        return func.__module__ + "." + func.__qualname__
    _class = type(func)
    return _class.__module__ + "." + _class.__qualname__
