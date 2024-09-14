# ruff: noqa: TRY301
from __future__ import annotations

from typing import Any

import pytest

from timeout_executor.serde import (
    SerializedError,
    deserialize_error,
    dumps_error,
    loads_error,
    serialize_error,
)


def test_serialize_error():
    try:
        raise ValueError("Test error")
    except ValueError as e:
        serialized = serialize_error(e)
        assert isinstance(serialized, SerializedError)
        assert isinstance(serialized.arg_exception, tuple)
        assert isinstance(serialized.arg_tracebacks, tuple)
        assert isinstance(serialized.reduce_mapping, dict)


def test_deserialize_error():
    try:
        raise ValueError("Test error")
    except ValueError as e:
        serialized = serialize_error(e)
        deserialized = deserialize_error(serialized)
        assert isinstance(deserialized, ValueError)
        assert str(deserialized) == "Test error"


def test_dumps_error():
    try:
        raise ValueError("Test error")
    except ValueError as e:
        dumped = dumps_error(e)
        assert isinstance(dumped, bytes)


def test_loads_error():
    try:
        raise ValueError("Test error")
    except ValueError as e:
        dumped = dumps_error(e)
        loaded = loads_error(dumped)
        assert isinstance(loaded, ValueError)
        assert str(loaded) == "Test error"


def test_serialize_and_deserialize_nested_error():
    try:
        try:
            raise ValueError("Inner error")
        except ValueError as inner:
            raise RuntimeError("Outer error") from inner
    except RuntimeError as outer:
        serialized = serialize_error(outer)
        deserialized = deserialize_error(serialized)
        assert isinstance(deserialized, RuntimeError)
        assert str(deserialized) == "Outer error"
        assert deserialized.__cause__
        assert isinstance(deserialized.__cause__, ValueError)
        assert str(deserialized.__cause__) == "Inner error"


def test_dumps_and_loads_nested_error():
    try:
        try:
            raise ValueError("Inner error")
        except ValueError as inner:
            raise RuntimeError("Outer error") from inner
    except RuntimeError as outer:
        dumped = dumps_error(outer)
        loaded = loads_error(dumped)
        assert isinstance(loaded, RuntimeError)
        assert str(loaded) == "Outer error"
        assert loaded.__cause__
        assert isinstance(loaded.__cause__, ValueError)
        assert str(loaded.__cause__) == "Inner error"


def test_loads_error_non_serialized():
    some_value: Any = object()

    with pytest.raises(TypeError, match=r"error is not SerializedError"):
        loads_error(some_value)
