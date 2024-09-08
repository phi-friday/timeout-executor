"""only using in subprocess"""

from __future__ import annotations

from functools import partial
from inspect import isawaitable
from os import environ
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

import anyio
import cloudpickle
from anyio.lowlevel import checkpoint

from timeout_executor.const import TIMEOUT_EXECUTOR_INPUT_FILE

if TYPE_CHECKING:
    from typing_extensions import ParamSpec, TypeVar

    P = ParamSpec("P")
    T = TypeVar("T", infer_variance=True)

__all__ = []


def run_in_subprocess() -> None:
    input_file = Path(environ.get(TIMEOUT_EXECUTOR_INPUT_FILE, ""))
    with input_file.open("rb") as file_io:
        func, args, kwargs, output_file = cloudpickle.load(file_io)

    new_func = output_to_file(output_file)(func)
    new_func(*args, **kwargs)


def dumps_value(value: Any) -> bytes:
    if isinstance(value, BaseException):
        from timeout_executor.serde import dumps_error

        return dumps_error(value)
    return cloudpickle.dumps(value)


def output_to_file(file: str) -> Callable[[Callable[P, T]], Callable[P, T]]:
    def wrapper(func: Callable[P, T]) -> Callable[P, T]:
        func = wrap_function_as_sync(func)

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
                with open(file, "wb+") as file_io:  # noqa: PTH123
                    file_io.write(dump)

        return inner

    return wrapper


def wrap_function_as_async(func: Callable[P, Any]) -> Callable[P, Any]:
    async def wrapped(*args: P.args, **kwargs: P.kwargs) -> Any:
        await checkpoint()
        result = func(*args, **kwargs)
        if isawaitable(result):
            return await result
        return result

    return wrapped


def wrap_function_as_sync(func: Callable[P, Any]) -> Callable[P, Any]:
    async_wrapped = wrap_function_as_async(func)

    def wrapped(*args: P.args, **kwargs: P.kwargs) -> Any:
        new_func = partial(async_wrapped, *args, **kwargs)
        return anyio.run(new_func)

    return wrapped
