"""only using in subprocess"""

from __future__ import annotations

from inspect import iscoroutinefunction
from os import environ
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

import anyio
import cloudpickle
from typing_extensions import ParamSpec, TypeAlias, TypeVar

from timeout_executor.const import TIMEOUT_EXECUTOR_INPUT_FILE
from timeout_executor.serde import dumps_error

if TYPE_CHECKING:
    from collections.abc import Awaitable, Coroutine

__all__ = []

P = ParamSpec("P")
T = TypeVar("T", infer_variance=True)
AnyAwaitable: TypeAlias = "Awaitable[T] | Coroutine[Any, Any, T]"


def run_in_subprocess() -> None:
    input_file = Path(environ.get(TIMEOUT_EXECUTOR_INPUT_FILE, ""))
    with input_file.open("rb") as file_io:
        func, args, kwargs, output_file = cloudpickle.load(file_io)
    new_func = output_to_file(output_file)(func)

    if iscoroutinefunction(new_func):
        from async_wrapper import async_to_sync

        new_func = async_to_sync(new_func)

    new_func(*args, **kwargs)


def dumps_value(value: Any) -> bytes:
    if isinstance(value, BaseException):
        return dumps_error(value)
    return cloudpickle.dumps(value)


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
        def inner(*args: P.args, **kwargs: P.kwargs) -> T:
            dump = b""
            try:
                result = func(*args, **kwargs)
            except BaseException as exc:
                dump = dumps_value(exc)
                raise
            else:
                dump = dumps_value(result)
                return result
            finally:
                with file.open("wb+") as file_io:
                    file_io.write(dump)

        return inner

    return wrapper


def _output_to_file_async(
    file: Path | anyio.Path,
) -> Callable[[Callable[P, AnyAwaitable[T]]], Callable[P, Coroutine[Any, Any, T]]]:
    if isinstance(file, Path):
        file = anyio.Path(file)

    def wrapper(
        func: Callable[P, AnyAwaitable[T]],
    ) -> Callable[P, Coroutine[Any, Any, T]]:
        async def inner(*args: P.args, **kwargs: P.kwargs) -> T:
            dump = b""
            try:
                result = await func(*args, **kwargs)
            except BaseException as exc:
                dump = dumps_value(exc)
                raise
            else:
                dump = dumps_value(result)
                return result
            finally:
                async with await file.open("wb+") as file_io:
                    await file_io.write(dump)

        return inner

    return wrapper
