from __future__ import annotations

import sys
from collections import deque
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass
from operator import itemgetter
from types import TracebackType
from typing import TYPE_CHECKING, Any

import cloudpickle
from tblib import Traceback
from tblib.pickling_support import pickle_exception, unpickle_exception
from typing_extensions import TypeAlias

if TYPE_CHECKING:
    SerializedTraceback: TypeAlias = dict[str, Any]

__all__ = ["dumps_error", "loads_error", "serialize_error", "deserialize_error"]

_DATACLASS_FROZEN_KWARGS: dict[str, bool] = {"frozen": True}
if sys.version_info >= (3, 10):  # pragma: no cover
    _DATACLASS_FROZEN_KWARGS.update({"kw_only": True, "slots": True})


@dataclass(**_DATACLASS_FROZEN_KWARGS)
class SerializedError:
    arg_exception: tuple[Any, ...]
    arg_tracebacks: tuple[tuple[int, SerializedTraceback], ...]

    reduce_mapping: dict[str, bytes | SerializedTraceback | SerializedError]
    # TODO: reduce_args: tuple[Any, ...]


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
    reduce_args = exception[1:]

    arg_result: deque[Any] = deque()
    arg_tracebacks: deque[tuple[int, SerializedTraceback]] = deque()

    # __reduce_ex__ args[0, 1], cause, tb [, context, suppress_context, notes])
    for index, value in enumerate(exception_args):
        if not isinstance(value, (TracebackType, Traceback)):
            arg_result.append(value)
            continue
        new = _serialize_traceback(value)
        arg_tracebacks.append((index, new))

    reduce_arg = None
    if reduce_args:
        reduce_arg, reduce_args = reduce_args[0], reduce_args[1:]

    reduce_mapping: dict[str, bytes | SerializedTraceback | SerializedError] = {}
    if isinstance(reduce_arg, Mapping):
        for key, value in reduce_arg.items():
            if isinstance(value, (TracebackType, Traceback)):
                reduce_mapping[key] = _serialize_traceback(value)
                continue
            if isinstance(value, BaseException):
                reduce_mapping[key] = serialize_error(value)
                continue

            with suppress(Exception):
                reduce_mapping[key] = cloudpickle.dumps(value)

    # TODO: ... __reduce_ex__ args[3:]
    return SerializedError(
        arg_exception=tuple(arg_result),
        arg_tracebacks=tuple(arg_tracebacks),
        reduce_mapping=reduce_mapping,
    )


def deserialize_error(error: SerializedError) -> BaseException:
    """deserialize exception"""
    arg_exception: deque[Any] = deque(error.arg_exception)
    arg_tracebacks: deque[tuple[int, SerializedTraceback]] = deque(error.arg_tracebacks)

    for salt, (index, value) in enumerate(sorted(arg_tracebacks, key=itemgetter(0))):
        traceback = _deserialize_traceback(value)
        arg_exception.insert(index + salt, traceback)

    result = unpickle_exception(*arg_exception)

    for key, value in error.reduce_mapping.items():
        if isinstance(value, SerializedError):
            new = deserialize_error(value)
        elif isinstance(value, dict):
            new = _deserialize_traceback(value)
        else:
            new = cloudpickle.loads(value)
        setattr(result, key, new)

    return result


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


def _serialize_traceback(traceback: TracebackType | Traceback) -> SerializedTraceback:
    if not isinstance(traceback, Traceback):
        traceback = Traceback(traceback)
    return traceback.as_dict()


def _deserialize_traceback(
    serialized_traceback: SerializedTraceback,
) -> TracebackType | None:
    traceback = Traceback.from_dict(serialized_traceback)
    return traceback.as_traceback()
