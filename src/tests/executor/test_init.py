from __future__ import annotations

import uuid

import pytest

from timeout_executor import TimeoutExecutor


@pytest.fixture
def key() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def value() -> str:
    return str(uuid.uuid4())


def test_init_func(key, value):
    executor = TimeoutExecutor(1)
    executor.set_initializer(sample_init, key, value=value)
    assert executor.initializer is not None
    assert executor.initializer.function is sample_init
    assert executor.initializer.args == (key,)
    assert executor.initializer.kwargs == {"value": value}

    async_result = executor.apply(get_init_if_exist, key)
    result = async_result.result()
    assert isinstance(result, str)
    assert result == value


def test_unset_init_func(key, value):
    executor = TimeoutExecutor(1)
    executor.set_initializer(sample_init, key, value=value)

    assert executor.initializer is not None
    assert executor.initializer.function is sample_init
    assert executor.initializer.args == (key,)
    assert executor.initializer.kwargs == {"value": value}

    executor.unset_initializer()
    assert executor.initializer is None

    async_result = executor.apply(get_init_if_exist, key)
    result = async_result.result()
    assert isinstance(result, str)
    assert result != value
    assert not result


def sample_init(key: str, *, value: str) -> None:
    import os

    os.environ[key.upper()] = value


def get_init_if_exist(key: str) -> str:
    import os

    return os.environ.get(key.upper(), "")
