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

__all__ = ["TimeoutExecutor", "apply_func", "delay_func"]

P = ParamSpec("P")
T = TypeVar("T", infer_variance=True)
P2 = ParamSpec("P2")
T2 = TypeVar("T2", infer_variance=True)


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
        return shlex.split(f'{sys.executable} -c "{SUBPROCESS_COMMAND}"')

    def apply(self, *args: P.args, **kwargs: P.kwargs) -> AsyncResult[T]:
        input_file, output_file = self._create_temp_files()

        input_args = (self._func, args, kwargs, output_file)
        input_args_as_bytes = cloudpickle.dumps(input_args)
        with input_file.open("wb+") as file:
            file.write(input_args_as_bytes)

        command = self._command()
        process = subprocess.Popen(
            command,  # noqa: S603
            env={TIMEOUT_EXECUTOR_INPUT_FILE: input_file.as_posix()},
            stdin=subprocess.DEVNULL,
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
        process = subprocess.Popen(  # noqa: ASYNC101
            command,  # noqa: S603
            env={TIMEOUT_EXECUTOR_INPUT_FILE: input_file.as_posix()},
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return AsyncResult(process, input_file, output_file, self._timeout)


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
    executor = _Executor(timeout, func)
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
    executor = _Executor(timeout, func)
    return await executor.delay(*args, **kwargs)


class TimeoutExecutor:
    """timeout executor"""

    def __init__(self, timeout: float) -> None:
        self._timeout = timeout

    def _create_executor(self, func: Callable[P, T]) -> _Executor[P, T]:
        return _Executor(self._timeout, func)

    @overload
    def apply(
        self,
        func: Callable[P, Coroutine[Any, Any, T]],
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> AsyncResult[T]: ...
    @overload
    def apply(
        self, func: Callable[P, T], *args: P.args, **kwargs: P.kwargs
    ) -> AsyncResult[T]: ...
    def apply(
        self, func: Callable[P, Any], *args: P.args, **kwargs: P.kwargs
    ) -> AsyncResult[Any]:
        """run function with deadline

        Args:
            func: func(sync or async)

        Returns:
            async result container
        """
        return apply_func(self._timeout, func, *args, **kwargs)

    @overload
    async def delay(
        self,
        func: Callable[P, Coroutine[Any, Any, T]],
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> AsyncResult[T]: ...
    @overload
    async def delay(
        self, func: Callable[P, T], *args: P.args, **kwargs: P.kwargs
    ) -> AsyncResult[T]: ...
    async def delay(
        self, func: Callable[P, Any], *args: P.args, **kwargs: P.kwargs
    ) -> AsyncResult[Any]:
        """run function with deadline

        Args:
            func: func(sync or async)

        Returns:
            async result container
        """
        return await delay_func(self._timeout, func, *args, **kwargs)

    @overload
    async def apply_async(
        self,
        func: Callable[P, Coroutine[Any, Any, T]],
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> AsyncResult[T]: ...
    @overload
    async def apply_async(
        self, func: Callable[P, T], *args: P.args, **kwargs: P.kwargs
    ) -> AsyncResult[T]: ...
    async def apply_async(
        self, func: Callable[P, Any], *args: P.args, **kwargs: P.kwargs
    ) -> AsyncResult[Any]:
        """run function with deadline.

        alias of `delay`

        Args:
            func: func(sync or async)

        Returns:
            async result container
        """
        return await self.delay(func, *args, **kwargs)
