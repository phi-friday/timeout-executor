from __future__ import annotations

import asyncio
import time
from itertools import product
from typing import Any

import anyio
import pytest

from timeout_executor import AsyncResult, TimeoutExecutor

TEST_SIZE = 3


class TestExecutorSync:
    @pytest.mark.parametrize(("x", "y"), product(range(TEST_SIZE), range(TEST_SIZE)))
    def test_apply_args(self, x: int, y: int):
        executor = TimeoutExecutor(1)
        result = executor.apply(sample_func, x, y)
        assert isinstance(result, AsyncResult)
        result = result.result()
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert not result[1]
        assert isinstance(result[0], tuple)
        assert result[0] == (x, y)

    @pytest.mark.parametrize(("x", "y"), product(range(TEST_SIZE), range(TEST_SIZE)))
    def test_apply_kwargs(self, *, x: int, y: int):
        executor = TimeoutExecutor(1)
        result = executor.apply(sample_func, x=x, y=y)
        assert isinstance(result, AsyncResult)
        result = result.result()
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert not result[0]
        assert isinstance(result[1], dict)
        assert result[1] == {"x": x, "y": y}

    def test_apply_timeout(self):
        executor = TimeoutExecutor(1)
        result = executor.apply(time.sleep, 1.5)
        assert isinstance(result, AsyncResult)
        pytest.raises(TimeoutError, result.result)

    @pytest.mark.parametrize("x", range(TEST_SIZE))
    def test_apply_lambda(self, x: int):
        executor = TimeoutExecutor(1)
        result = executor.apply(lambda: x)
        assert isinstance(result, AsyncResult)
        result = result.result()
        assert isinstance(result, int)
        assert result == x

    @pytest.mark.parametrize("x", range(TEST_SIZE))
    def test_apply_lambda_error(self, x: int):
        executor = TimeoutExecutor(1)

        def temp_func(x: int) -> None:
            raise RuntimeError(x)

        lambda_func = lambda: temp_func(x)  # noqa: E731
        result = executor.apply(lambda_func)
        assert isinstance(result, AsyncResult)
        pytest.raises(RuntimeError, result.result)

    def test_terminator(self):
        executor = TimeoutExecutor(0.5)

        def temp_func() -> None:
            time.sleep(1)

        result = executor.apply(temp_func)
        assert isinstance(result, AsyncResult)
        pytest.raises(TimeoutError, result.result)

        assert result._terminator.is_active is True  # noqa: SLF001


@pytest.mark.anyio()
class TestExecutorAsync:
    @pytest.mark.parametrize(("x", "y"), product(range(TEST_SIZE), range(TEST_SIZE)))
    async def test_apply_args(self, x: int, y: int):
        executor = TimeoutExecutor(1)
        result = await executor.delay(sample_async_func, x, y)
        assert isinstance(result, AsyncResult)
        result = await result.delay()
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert not result[1]
        assert isinstance(result[0], tuple)
        assert result[0] == (x, y)

    @pytest.mark.parametrize(("x", "y"), product(range(TEST_SIZE), range(TEST_SIZE)))
    async def test_apply_kwargs(self, *, x: int, y: int):
        executor = TimeoutExecutor(1)
        result = await executor.delay(sample_async_func, x=x, y=y)
        assert isinstance(result, AsyncResult)
        result = await result.delay()
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert not result[0]
        assert isinstance(result[1], dict)
        assert result[1] == {"x": x, "y": y}

    async def test_apply_timeout(self):
        executor = TimeoutExecutor(1)
        result = await executor.delay(anyio.sleep, 1.5)
        try:
            await result.delay(0.1)
        except Exception as exc:  # noqa: BLE001
            assert isinstance(exc, TimeoutError)  # noqa: PT017
        else:
            raise Exception("TimeoutError does not occur")  # noqa: TRY002

    @pytest.mark.parametrize("x", range(TEST_SIZE))
    async def test_apply_lambda(self, x: int):
        executor = TimeoutExecutor(1)

        async def lambdalike() -> int:
            await asyncio.sleep(0.1)
            return x

        result = await executor.delay(lambdalike)
        assert isinstance(result, AsyncResult)
        result = await result.delay()
        assert isinstance(result, int)
        assert result == x

    async def test_apply_lambda_error(self):
        executor = TimeoutExecutor(1)

        async def lambdalike() -> int:
            await asyncio.sleep(10)
            raise RuntimeError("error")

        result = await executor.delay(lambdalike)
        try:
            await result.delay(0.1)
        except Exception as exc:  # noqa: BLE001
            assert isinstance(exc, TimeoutError)  # noqa: PT017
        else:
            raise Exception("TimeoutError does not occur")  # noqa: TRY002

    async def test_terminator(self):
        executor = TimeoutExecutor(0.5)

        async def temp_func() -> None:
            await anyio.sleep(1)

        result = await executor.delay(temp_func)
        assert isinstance(result, AsyncResult)
        try:
            await result.delay()
        except Exception as exc:  # noqa: BLE001
            assert isinstance(exc, TimeoutError)  # noqa: PT017
        else:
            raise Exception("TimeoutError does not occur")  # noqa: TRY002

        assert result._terminator.is_active is True  # noqa: SLF001


def sample_func(*args: Any, **kwargs: Any) -> tuple[tuple[Any, ...], dict[str, Any]]:
    return args, kwargs


async def sample_async_func(
    *args: Any, **kwargs: Any
) -> tuple[tuple[Any, ...], dict[str, Any]]:
    await asyncio.sleep(0.1)

    return sample_func(*args, **kwargs)
