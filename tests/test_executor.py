from __future__ import annotations

import asyncio
import sys
import time
from collections import deque
from functools import partial
from itertools import combinations, product
from pickle import PicklingError
from typing import Any, Callable

import anyio
import pytest
from anyio.abc import ObjectSendStream

from timeout_executor import TimeoutExecutor
from timeout_executor.concurrent.main import BackendType
from timeout_executor.serde.main import PicklerType

if sys.version_info < (3, 11):
    from exceptiongroup import ExceptionGroup  # type: ignore

TEST_SIZE = 3


class TestExecutorSync:
    @pytest.mark.parametrize(("x", "y"), product(range(TEST_SIZE), range(TEST_SIZE)))
    def test_apply_args(self, x: int, y: int):
        executor = TimeoutExecutor(1)
        result = executor.apply(sample_func, x, y)
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert not result[1]
        assert isinstance(result[0], tuple)
        assert result[0] == (x, y)

    @pytest.mark.parametrize(("x", "y"), product(range(TEST_SIZE), range(TEST_SIZE)))
    def test_apply_kwargs(self, *, x: int, y: int):
        executor = TimeoutExecutor(1)
        result = executor.apply(sample_func, x=x, y=y)
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert not result[0]
        assert isinstance(result[1], dict)
        assert result[1] == {"x": x, "y": y}

    @pytest.mark.parametrize("x", range(TEST_SIZE))
    def test_apply_init(self, x: int):
        executor = TimeoutExecutor(1)
        name = f"x_{x}"
        alter_left, alter_right = f"x_{x - 1}", f"x_{x + 1}"
        executor.set_init(sample_init_set, **{name: x})
        result = executor.apply(sample_init_get, name, alter_left, alter_right)
        assert isinstance(result, dict)
        assert result
        assert result.get(name) == str(x)
        assert result.get(alter_left) is None
        assert result.get(alter_right) is None

    def test_apply_timeout(self):
        executor = TimeoutExecutor(1)
        executor.apply(time.sleep, 0.5)
        pytest.raises(TimeoutError, executor.apply, time.sleep, 1.5)

    @pytest.mark.parametrize(
        ("backend", "pickler", "x"),
        product(  # pyright: ignore[reportCallIssue]
            ("billiard", "multiprocessing", "loky"),
            ("dill", "cloudpickle"),
            range(TEST_SIZE),  # pyright: ignore[reportArgumentType]
        ),
    )
    def test_apply_lambda(self, backend: BackendType, pickler: PicklerType, x: int):
        executor = TimeoutExecutor(1, backend, pickler=pickler)
        result = executor.apply(lambda: x)
        assert isinstance(result, int)
        assert result == x

    @pytest.mark.parametrize("x", range(TEST_SIZE))
    def test_apply_lambda_error(self, x: int):
        executor = TimeoutExecutor(1, backend="multiprocessing", pickler="pickle")
        pytest.raises((PicklingError, AttributeError), executor.apply, lambda: x)


@pytest.mark.asyncio()
class TestExecutorAsync:
    @pytest.mark.parametrize(("x", "y"), product(range(TEST_SIZE), range(TEST_SIZE)))
    async def test_apply_args(self, x: int, y: int):
        executor = TimeoutExecutor(1)
        result = await executor.apply_async(sample_async_func, x, y)
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert not result[1]
        assert isinstance(result[0], tuple)
        assert result[0] == (x, y)

    @pytest.mark.parametrize(("x", "y"), product(range(TEST_SIZE), range(TEST_SIZE)))
    async def test_apply_kwargs(self, *, x: int, y: int):
        executor = TimeoutExecutor(1)
        result = await executor.apply_async(sample_async_func, x=x, y=y)
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert not result[0]
        assert isinstance(result[1], dict)
        assert result[1] == {"x": x, "y": y}

    @pytest.mark.parametrize(("x", "y"), combinations(range(TEST_SIZE * 2), 2))
    async def test_apply_gather(self, *, x: int, y: int):
        executor = TimeoutExecutor(1)

        send, recv = anyio.create_memory_object_stream()
        result = deque()
        with executor.lock:
            async with anyio.create_task_group() as task_group:
                async with send:
                    task_group.start_soon(
                        send_result,
                        send.clone(),
                        executor.apply_async,
                        partial(sample_async_func, y=y),
                        x,
                    )
                    task_group.start_soon(
                        send_result,
                        send.clone(),
                        executor.apply_async,
                        partial(sample_async_func, x=x),
                        y,
                    )
                async with recv:
                    async for value in recv:
                        result.append(value)

        assert len(result) == 2
        for value in result:
            assert isinstance(value, tuple)
            assert len(value) == 2
            assert isinstance(value[0], tuple)
            assert isinstance(value[1], dict)
            assert value[0]
            assert value[1]
            if value[0][0] == x:
                assert "y" in value[1]
                assert value[1]["y"] == y
            else:
                assert "x" in value[1]
                assert value[1]["x"] == x

    @pytest.mark.parametrize("x", range(TEST_SIZE))
    async def test_apply_init(self, x: int):
        executor = TimeoutExecutor(1)
        name = f"x_{x}"
        alter_left, alter_right = f"x_{x - 1}", f"x_{x + 1}"
        executor.set_init(sample_init_set, **{name: x})
        result = await executor.apply_async(
            sample_init_async_get, name, alter_left, alter_right
        )
        assert isinstance(result, dict)
        assert result
        assert result.get(name) == str(x)
        assert result.get(alter_left) is None
        assert result.get(alter_right) is None

    async def test_apply_timeout(self):
        executor = TimeoutExecutor(1)
        await executor.apply_async(asyncio.sleep, 0.5)
        try:
            await executor.apply_async(asyncio.sleep, 1.5)
        except ExceptionGroup as exc_group:
            for exc in exc_group.exceptions:
                assert isinstance(exc, TimeoutError)
        except Exception as exc:  # noqa: BLE001
            assert isinstance(exc, TimeoutError)  # noqa: PT017
        else:
            raise Exception("TimeoutError does not occur")  # noqa: TRY002

    @pytest.mark.parametrize(
        ("backend", "pickler", "x"),
        product(  #  pyright: ignore[reportCallIssue]
            ("billiard", "multiprocessing", "loky"),
            ("dill", "cloudpickle"),
            range(TEST_SIZE),  # pyright: ignore[reportArgumentType]
        ),
    )
    async def test_apply_lambda(
        self, backend: BackendType, pickler: PicklerType, x: int
    ):
        executor = TimeoutExecutor(1, backend, pickler=pickler)

        async def lambdalike() -> int:
            await asyncio.sleep(0.1)
            return x

        result = await executor.apply_async(lambdalike)
        assert isinstance(result, int)
        assert result == x

    @pytest.mark.parametrize("x", range(TEST_SIZE))
    async def test_apply_lambda_error(self, x: int):
        executor = TimeoutExecutor(1, backend="multiprocessing", pickler="pickle")

        async def lambdalike() -> int:
            await asyncio.sleep(0.1)
            return x

        try:
            await executor.apply_async(lambdalike)
        except Exception as exc:  # noqa: BLE001
            assert isinstance(exc, (PicklingError, AttributeError))  # noqa: PT017
        else:
            raise Exception("PicklingError does not occur")  # noqa: TRY002


def sample_func(*args: Any, **kwargs: Any) -> tuple[tuple[Any, ...], dict[str, Any]]:
    return args, kwargs


async def sample_async_func(
    *args: Any, **kwargs: Any
) -> tuple[tuple[Any, ...], dict[str, Any]]:
    await asyncio.sleep(0.1)
    return sample_func(*args, **kwargs)


def sample_init_set(**kwargs: Any) -> None:
    from os import environ

    for key, value in kwargs.items():
        environ.setdefault(key, str(value))


def sample_init_get(*names: str) -> dict[str, Any]:
    from os import environ

    return {name: environ.get(name, None) for name in names}


async def sample_init_async_get(*names: str) -> dict[str, Any]:
    await asyncio.sleep(0.1)
    return sample_init_get(*names)


async def send_result(
    stream: ObjectSendStream[Any], func: Callable[..., Any], *args: Any, **kwargs: Any
) -> None:
    async with stream:
        result = await func(*args, **kwargs)
        await stream.send(result)
