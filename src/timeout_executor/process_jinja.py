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

from timeout_executor.const import (
    TIMEOUT_EXECUTOR_INIT_FILE,
    TIMEOUT_EXECUTOR_INPUT_FILE,
)

if TYPE_CHECKING:
    from typing_extensions import ParamSpec, TypeVar

    P = ParamSpec("P")
    T = TypeVar("T", infer_variance=True)

__all__ = []


def run_in_subprocess() -> None:
    init_file = environ.get(TIMEOUT_EXECUTOR_INIT_FILE, "")
    if init_file:
        with Path(init_file).open("rb") as file_io:
            _, init_args, init_kwargs = cloudpickle.load(file_io)
        init_func(*init_args, **init_kwargs)  # type: ignore  # noqa: F821

    input_file = Path(environ.get(TIMEOUT_EXECUTOR_INPUT_FILE, ""))
    with input_file.open("rb") as file_io:
        _, args, kwargs, output_file = cloudpickle.load(file_io)

    new_func = output_to_file(output_file)(func)  # type: ignore # noqa: F821
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


###

python = str
text: python = """
def init_func(*args: Any, **kwargs: Any) -> None:
{{ init_func_code }}
    {{ init_func_name }}(*args, **kwargs)

def func(*args: Any, **kwargs: Any) -> Any:
{{ func_code }}
    return {{ func_name }}(*args, **kwargs)
"""
exec(text)  # noqa: S102

if __name__ == "__main__":
    run_in_subprocess()
