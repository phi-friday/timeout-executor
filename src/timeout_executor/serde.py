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

    # TODO: reduce_args: tuple[Any, ...]


def serialize_traceback(traceback: TracebackType) -> tuple[Any, ...]:
    return pickle_traceback(traceback)


def serialize_error(error: BaseException) -> SerializedError:
    """serialize exception"""
    # - unpickle func,
    # + (__reduce_ex__ args[0, 1], cause, tb [, context, suppress_context, notes]),
    # + ... __reduce_ex__ args[2:]
    exception = pickle_exception(error)[1:]

    # exception_args
    #   __reduce_ex__ args[0, 1], cause, tb [, context, suppress_context, notes])
    exception_args = exception[0]
    # reduce_args: ... __reduce_ex__ args[2:]
    # reduce_args = exception[1:]  # noqa: ERA001

    arg_result: deque[Any] = deque()
    arg_tracebacks: deque[tuple[int, tuple[Any, ...]]] = deque()

    # __reduce_ex__ args[0, 1], cause, tb [, context, suppress_context, notes])
    for index, value in enumerate(exception_args):
        if not isinstance(value, TracebackType):
            arg_result.append(value)
            continue
        new = serialize_traceback(value)[1]
        arg_tracebacks.append((index, new))

    # TODO: ... __reduce_ex__ args[2:]
    return SerializedError(
        arg_exception=tuple(arg_result), arg_tracebacks=tuple(arg_tracebacks)
    )


def deserialize_error(error: SerializedError) -> BaseException:
    """deserialize exception"""
    arg_exception: deque[Any] = deque(error.arg_exception)
    arg_tracebacks: deque[tuple[int, tuple[Any, ...]]] = deque(error.arg_tracebacks)

    for salt, (index, value) in enumerate(sorted(arg_tracebacks, key=itemgetter(0))):
        traceback = unpickle_traceback(*value)
        arg_exception.insert(index + salt, traceback)

    return unpickle_exception(*arg_exception)


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
