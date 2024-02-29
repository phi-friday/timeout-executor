"""only using in subprocess"""

from __future__ import annotations

from functools import wraps
from inspect import iscoroutinefunction
from os import environ
from pathlib import Path
from typing import Any, Callable, Coroutine

import anyio
import cloudpickle
from async_wrapper import async_to_sync
from typing_extensions import ParamSpec, TypeVar

from timeout_executor.const import TIMEOUT_EXECUTOR_INPUT_FILE
from timeout_executor.serde import dumps_error

__all__ = []

P = ParamSpec("P")
T = TypeVar("T", infer_variance=True)


def run_in_subprocess() -> None:
    input_file = Path(environ.get(TIMEOUT_EXECUTOR_INPUT_FILE, ""))
    with input_file.open("rb") as file_io:
        func, args, kwargs, output_file = cloudpickle.load(file_io)
    new_func = output_to_file(output_file)(func)

    if iscoroutinefunction(new_func):
        new_func = async_to_sync(new_func)

    new_func(*args, **kwargs)


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
            dump = b""
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
            dump = b""
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
