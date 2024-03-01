from __future__ import annotations

import sys
from collections import deque
from dataclasses import dataclass
from operator import itemgetter
from types import TracebackType
from typing import Any

import cloudpickle
from tblib.pickling_support import (
    pickle_exception,
    pickle_traceback,
    unpickle_exception,
    unpickle_traceback,
)

__all__ = ["dumps_error", "loads_error", "serialize_error", "deserialize_error"]

_DATACLASS_FROZEN_KWARGS: dict[str, bool] = {"frozen": True}
if sys.version_info >= (3, 10):
    _DATACLASS_FROZEN_KWARGS.update({"kw_only": True, "slots": True})

SENTINEL = object()


@dataclass(**_DATACLASS_FROZEN_KWARGS)
class SerializedError:
    arg_exception: tuple[Any, ...]
    arg_tracebacks: tuple[tuple[int, tuple[Any, ...]], ...]

    exception: tuple[Any, ...]
    tracebacks: tuple[tuple[int, tuple[Any, ...]], ...]


def serialize_traceback(traceback: TracebackType) -> tuple[Any, ...]:
    return pickle_traceback(traceback)


def serialize_error(error: BaseException) -> SerializedError:
    """serialize exception"""
    exception = pickle_exception(error)[1:]

    exception_args, exception = exception[0], exception[1:]

    arg_result: deque[Any] = deque()
    arg_tracebacks: deque[tuple[int, tuple[Any, ...]]] = deque()

    exception_result: deque[Any] = deque()
    tracebacks: deque[tuple[int, tuple[Any, ...]]] = deque()

    for result, tb_result, args in zip(
        (arg_result, exception_result),
        (arg_tracebacks, tracebacks),
        (exception_args, exception),
    ):
        for index, value in enumerate(args):
            if not isinstance(value, TracebackType):
                result.append(value)
                continue
            new = serialize_traceback(value)[1]
            tb_result.append((index, new))

    return SerializedError(
        arg_exception=tuple(arg_result),
        arg_tracebacks=tuple(arg_tracebacks),
        exception=tuple(exception_result),
        tracebacks=tuple(tracebacks),
    )


def deserialize_error(error: SerializedError) -> BaseException:
    """deserialize exception"""
    arg_exception: deque[Any] = deque(error.arg_exception)
    arg_tracebacks: deque[tuple[int, tuple[Any, ...]]] = deque(error.arg_tracebacks)

    exception: deque[Any] = deque(error.exception)
    tracebacks: deque[tuple[int, tuple[Any, ...]]] = deque(error.tracebacks)

    for result, tb_result in zip(
        (arg_exception, exception), (arg_tracebacks, tracebacks)
    ):
        for salt, (index, value) in enumerate(sorted(tb_result, key=itemgetter(0))):
            traceback = unpickle_traceback(*value)
            result.insert(index + salt, traceback)

    return unpickle_exception(*arg_exception, *exception)


def dumps_error(error: BaseException | SerializedError) -> bytes:
    """serialize exception as bytes"""
    if not isinstance(error, SerializedError):
        error = serialize_error(error)

    return cloudpickle.dumps(error)


def loads_error(error: bytes | SerializedError) -> BaseException:
    """deserialize exception from bytes"""
    if isinstance(error, bytes):
        error = cloudpickle.loads(error)
    if not isinstance(error, SerializedError):
        error_msg = f"error is not SerializedError object: {type(error).__name__}"
        raise TypeError(error_msg)

    return deserialize_error(error)
