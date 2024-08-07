from __future__ import annotations

import shlex
import subprocess
import sys
import tempfile
from collections import deque
from contextlib import suppress
from functools import partial
from itertools import chain
from pathlib import Path
from types import FunctionType
from typing import TYPE_CHECKING, Any, Callable, Generic, overload
from uuid import UUID, uuid4

import anyio
import cloudpickle
from typing_extensions import ParamSpec, Self, TypeVar, override

from timeout_executor.const import SUBPROCESS_COMMAND, TIMEOUT_EXECUTOR_INPUT_FILE
from timeout_executor.logging import logger
from timeout_executor.result import AsyncResult
from timeout_executor.terminate import Terminator
from timeout_executor.types import Callback, CallbackArgs, ExecutorArgs, ProcessCallback

if TYPE_CHECKING:
    from collections.abc import Awaitable, Iterable

    from timeout_executor.main import TimeoutExecutor

__all__ = ["apply_func", "delay_func"]

P = ParamSpec("P")
T = TypeVar("T", infer_variance=True)
P2 = ParamSpec("P2")
T2 = TypeVar("T2", infer_variance=True)


class Executor(Callback[P, T], Generic[P, T]):
    def __init__(
        self,
        timeout: float,
        func: Callable[P, T],
        callbacks: Callable[[], Iterable[ProcessCallback[P, T]]] | None = None,
    ) -> None:
        self._timeout = timeout
        self._func = func
        self._func_name = func_name(func)
        self._unique_id = uuid4()
        self._init_callbacks = callbacks
        self._callbacks: deque[ProcessCallback[P, T]] = deque()

    @property
    def unique_id(self) -> UUID:
        return self._unique_id

    def _create_temp_files(self) -> tuple[Path, Path]:
        """create temp files for input and output"""
        temp_dir = Path(tempfile.gettempdir()) / "timeout_executor"
        temp_dir.mkdir(exist_ok=True)

        unique_dir = temp_dir / str(self.unique_id)
        unique_dir.mkdir(exist_ok=False)

        input_file = unique_dir / "input.b"
        output_file = unique_dir / "output.b"

        return input_file, output_file

    def _command(self, stacklevel: int = 2) -> list[str]:
        """create subprocess command"""
        command = f'{sys.executable} -c "{SUBPROCESS_COMMAND}"'
        logger.debug("%r command: %s", self, command, stacklevel=stacklevel)
        return shlex.split(command)

    def _dump_args(
        self, output_file: Path | anyio.Path, *args: P.args, **kwargs: P.kwargs
    ) -> bytes:
        """dump args and output file path to input file"""
        input_args = (self._func, args, kwargs, str(output_file))
        logger.debug("%r before dump input args", self)
        input_args_as_bytes = cloudpickle.dumps(input_args)
        logger.debug(
            "%r after dump input args :: size: %d", self, len(input_args_as_bytes)
        )
        return input_args_as_bytes

    def _create_process(
        self, input_file: Path | anyio.Path, stacklevel: int = 2
    ) -> subprocess.Popen[str]:
        """create new process"""
        command = self._command(stacklevel=stacklevel + 1)
        logger.debug("%r before create new process", self, stacklevel=stacklevel)
        process = subprocess.Popen(  # noqa: S603
            command,
            env={TIMEOUT_EXECUTOR_INPUT_FILE: input_file.as_posix()},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        logger.debug("%r process: %d", self, process.pid, stacklevel=stacklevel)
        return process

    def _create_executor_args(
        self,
        input_file: Path | anyio.Path,
        output_file: Path | anyio.Path,
        terminator: Terminator[P, T],
    ) -> ExecutorArgs[P, T]:
        """create executor args"""
        return ExecutorArgs(
            executor=self,
            func_name=self._func_name,
            terminator=terminator,
            input_file=input_file,
            output_file=output_file,
            timeout=self._timeout,
        )

    def _init_process(
        self,
        input_file: Path | anyio.Path,
        output_file: Path | anyio.Path,
        stacklevel: int = 2,
    ) -> AsyncResult[P, T]:
        """init process.

        before end process
        ---
        1. create terminator
        2. create process
        3. create result container
        4. setup terminator
        5. watch terminator

        after end process
        ---
        6. end process
        7. return result
        8. run terminator
        """
        logger.debug("%r before init process", self, stacklevel=stacklevel)
        executor_args_builder = partial(
            self._create_executor_args, input_file, output_file
        )
        terminator = Terminator(executor_args_builder, self.callbacks)
        process = self._create_process(input_file, stacklevel=stacklevel + 1)
        result: AsyncResult[P, T] = AsyncResult(process, terminator.executor_args)
        terminator.callback_args = CallbackArgs(process=process, result=result)
        terminator.start()
        logger.debug("%r after init process", self, stacklevel=stacklevel)
        return result

    def apply(self, *args: P.args, **kwargs: P.kwargs) -> AsyncResult[P, T]:
        """run function with deadline"""
        input_file, output_file = self._create_temp_files()
        input_args_as_bytes = self._dump_args(output_file, *args, **kwargs)

        logger.debug("%r before write input file", self)
        with input_file.open("wb+") as file:
            file.write(input_args_as_bytes)
        logger.debug("%r after write input file", self)

        return self._init_process(input_file, output_file)

    async def delay(self, *args: P.args, **kwargs: P.kwargs) -> AsyncResult[P, T]:
        """run function with deadline"""
        input_file, output_file = self._create_temp_files()
        input_file, output_file = anyio.Path(input_file), anyio.Path(output_file)
        input_args_as_bytes = self._dump_args(output_file, *args, **kwargs)

        logger.debug("%r before write input file", self)
        async with await input_file.open("wb+") as file:
            await file.write(input_args_as_bytes)
        logger.debug("%r after write input file", self)

        return self._init_process(input_file, output_file)

    @override
    def __repr__(self) -> str:
        return f"<{type(self).__name__}: {self._func_name}>"

    @override
    def callbacks(self) -> Iterable[ProcessCallback[P, T]]:
        if self._init_callbacks is None:
            return self._callbacks.copy()
        return chain(self._init_callbacks(), self._callbacks.copy())

    @override
    def add_callback(self, callback: ProcessCallback[P, T]) -> Self:
        self._callbacks.append(callback)
        return self

    @override
    def remove_callback(self, callback: ProcessCallback[P, T]) -> Self:
        with suppress(ValueError):
            self._callbacks.remove(callback)
        return self


@overload
def apply_func(
    timeout_or_executor: float | TimeoutExecutor,
    func: Callable[P2, Awaitable[T2]],
    *args: P2.args,
    **kwargs: P2.kwargs,
) -> AsyncResult[P2, T2]: ...


@overload
def apply_func(
    timeout_or_executor: float | TimeoutExecutor,
    func: Callable[P2, T2],
    *args: P2.args,
    **kwargs: P2.kwargs,
) -> AsyncResult[P2, T2]: ...


def apply_func(
    timeout_or_executor: float | TimeoutExecutor,
    func: Callable[P2, Any],
    *args: P2.args,
    **kwargs: P2.kwargs,
) -> AsyncResult[P2, Any]:
    """run function with deadline

    Args:
        timeout_or_executor: deadline
        func: func(sync or async)
        *args: func args
        **kwargs: func kwargs

    Returns:
        async result container
    """
    if isinstance(timeout_or_executor, (float, int)):
        executor = Executor(timeout_or_executor, func)
    else:
        executor = Executor(
            timeout_or_executor.timeout, func, timeout_or_executor.callbacks
        )
    return executor.apply(*args, **kwargs)


@overload
async def delay_func(
    timeout_or_executor: float | TimeoutExecutor,
    func: Callable[P2, Awaitable[T2]],
    *args: P2.args,
    **kwargs: P2.kwargs,
) -> AsyncResult[P2, T2]: ...


@overload
async def delay_func(
    timeout_or_executor: float | TimeoutExecutor,
    func: Callable[P2, T2],
    *args: P2.args,
    **kwargs: P2.kwargs,
) -> AsyncResult[P2, T2]: ...


async def delay_func(
    timeout_or_executor: float | TimeoutExecutor,
    func: Callable[P2, Any],
    *args: P2.args,
    **kwargs: P2.kwargs,
) -> AsyncResult[P2, Any]:
    """run function with deadline

    Args:
        timeout_or_executor: deadline
        func: func(sync or async)
        *args: func args
        **kwargs: func kwargs

    Returns:
        async result container
    """
    if isinstance(timeout_or_executor, (float, int)):
        executor = Executor(timeout_or_executor, func)
    else:
        executor = Executor(
            timeout_or_executor.timeout, func, timeout_or_executor.callbacks
        )
    return await executor.delay(*args, **kwargs)


def func_name(func: Callable[..., Any]) -> str:
    if isinstance(func, FunctionType) or is_class(func):
        return func.__module__ + "." + func.__qualname__
    _class = type(func)
    return _class.__module__ + "." + _class.__qualname__


def is_class(obj: Any) -> bool:
    if isinstance(obj, type):
        return True

    meta = type(obj)
    return issubclass(meta, type)
