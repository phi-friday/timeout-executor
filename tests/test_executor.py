from __future__ import annotations

import time
from itertools import product
from typing import Any

import anyio
import pytest

from timeout_executor import AsyncResult, TimeoutExecutor

TEST_SIZE = 3

pytestmark = pytest.mark.anyio


class BaseExecutorTest:
    @staticmethod
    def executor(timeout: float) -> TimeoutExecutor[Any]:
        return TimeoutExecutor(timeout)


class TestExecutorSync(BaseExecutorTest):
    @pytest.mark.parametrize(("x", "y"), product(range(TEST_SIZE), range(TEST_SIZE)))
    def test_apply_args(self, x: int, y: int):
        result = self.executor(1).apply(sample_func, x, y)
        assert isinstance(result, AsyncResult)
        result = result.result()
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert not result[1]
        assert isinstance(result[0], tuple)
        assert result[0] == (x, y)

    @pytest.mark.parametrize(("x", "y"), product(range(TEST_SIZE), range(TEST_SIZE)))
    def test_apply_kwargs(self, *, x: int, y: int):
        result = self.executor(1).apply(sample_func, x=x, y=y)
        assert isinstance(result, AsyncResult)
        result = result.result()
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert not result[0]
        assert isinstance(result[1], dict)
        assert result[1] == {"x": x, "y": y}

    def test_apply_timeout(self):
        result = self.executor(1).apply(time.sleep, 1.5)
        assert isinstance(result, AsyncResult)
        pytest.raises(TimeoutError, result.result)

    @pytest.mark.parametrize("x", range(TEST_SIZE))
    def test_apply_lambda(self, x: int):
        result = self.executor(1).apply(lambda: x)
        assert isinstance(result, AsyncResult)
        result = result.result()
        assert isinstance(result, int)
        assert result == x

    @pytest.mark.parametrize("x", range(TEST_SIZE))
    def test_apply_lambda_error(self, x: int):
        def temp_func(x: int) -> None:
            raise RuntimeError(x)

        lambda_func = lambda: temp_func(x)  # noqa: E731
        result = self.executor(1).apply(lambda_func)
        assert isinstance(result, AsyncResult)
        pytest.raises(RuntimeError, result.result)

    def test_terminator(self):
        def temp_func() -> None:
            time.sleep(1)

        result = self.executor(0.5).apply(temp_func)
        assert isinstance(result, AsyncResult)
        pytest.raises(TimeoutError, result.result)

        assert result._terminator.is_active is True  # noqa: SLF001


class TestExecutorAsync(BaseExecutorTest):
    @pytest.mark.parametrize(("x", "y"), product(range(TEST_SIZE), range(TEST_SIZE)))
    async def test_apply_args(self, x: int, y: int):
        result = await self.executor(1).delay(sample_async_func, x, y)
        assert isinstance(result, AsyncResult)
        result = await result.delay()
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert not result[1]
        assert isinstance(result[0], tuple)
        assert result[0] == (x, y)

    @pytest.mark.parametrize(("x", "y"), product(range(TEST_SIZE), range(TEST_SIZE)))
    async def test_apply_kwargs(self, *, x: int, y: int):
        result = await self.executor(1).delay(sample_async_func, x=x, y=y)
        assert isinstance(result, AsyncResult)
        result = await result.delay()
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert not result[0]
        assert isinstance(result[1], dict)
        assert result[1] == {"x": x, "y": y}

    async def test_apply_timeout(self):
        result = await self.executor(1).delay(anyio.sleep, 1.5)
        with pytest.raises(TimeoutError):
            await result.delay(0.1)

    @pytest.mark.parametrize("x", range(TEST_SIZE))
    async def test_apply_lambda(self, x: int):
        async def lambdalike() -> int:
            await anyio.sleep(0.1)
            return x

        result = await self.executor(1).delay(lambdalike)
        assert isinstance(result, AsyncResult)
        result = await result.delay()
        assert isinstance(result, int)
        assert result == x

    async def test_apply_lambda_error(self):
        async def lambdalike() -> int:
            await anyio.sleep(10)
            raise RuntimeError("error")

        result = await self.executor(1).delay(lambdalike)
        with pytest.raises(TimeoutError):
            await result.delay(0.1)

    async def test_terminator(self):
        async def temp_func() -> None:
            await anyio.sleep(1)

        result = await self.executor(0.5).delay(temp_func)
        assert isinstance(result, AsyncResult)
        with pytest.raises(TimeoutError):
            await result.delay()

        assert result._terminator.is_active is True  # noqa: SLF001


def sample_func(*args: Any, **kwargs: Any) -> tuple[tuple[Any, ...], dict[str, Any]]:
    return args, kwargs


async def sample_async_func(
    *args: Any, **kwargs: Any
) -> tuple[tuple[Any, ...], dict[str, Any]]:
    await anyio.sleep(0.1)

    return sample_func(*args, **kwargs)
