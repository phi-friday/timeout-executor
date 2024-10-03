from __future__ import annotations

import os
import uuid
from collections.abc import Awaitable
from itertools import product
from typing import Any

import pytest

from tests.executor.base import BaseExecutorTest
from timeout_executor import AsyncResult, TimeoutExecutor

TEST_SIZE = 3

pytestmark = pytest.mark.anyio


class TestExecutorSync(BaseExecutorTest):
    @pytest.mark.parametrize(
        ("x", "y"), list(product(range(TEST_SIZE), range(TEST_SIZE)))
    )
    def test_apply_args(self, x: int, y: int):
        result = self.executor(1).apply(self.sample_func, x, y)
        assert isinstance(result, AsyncResult)
        result = result.result()
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert not result[1]
        assert isinstance(result[0], tuple)
        assert result[0] == (x, y)

    @pytest.mark.parametrize(
        ("x", "y"), list(product(range(TEST_SIZE), range(TEST_SIZE)))
    )
    def test_apply_kwargs(self, *, x: int, y: int):
        result = self.executor(1).apply(self.sample_func, x=x, y=y)
        assert isinstance(result, AsyncResult)
        result = result.result()
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert not result[0]
        assert isinstance(result[1], dict)
        assert result[1] == {"x": x, "y": y}

    def test_apply_timeout(self):
        def sleep(x: float) -> None:
            import time

            time.sleep(x)

        result = self.executor(1).apply(sleep, 1.5)
        assert isinstance(result, AsyncResult)
        pytest.raises(TimeoutError, result.result)

    @pytest.mark.parametrize("x", range(TEST_SIZE))
    def test_apply_lambda_with_local_variable(self, x: int):
        if self.use_jinja:
            pytest.skip("JinjaExecutor does not support lambda.")

        result = self.executor(1).apply(lambda: x)
        assert isinstance(result, AsyncResult)
        result = result.result()
        assert isinstance(result, int)
        assert result == x

    @pytest.mark.parametrize("x", range(TEST_SIZE))
    def test_apply_lambda_error(self, x: int):
        if self.use_jinja:
            pytest.skip("JinjaExecutor does not support lambda.")

        def temp_func(x: int) -> None:
            raise RuntimeError(x)

        lambda_func = lambda: temp_func(x)  # noqa: E731
        result = self.executor(1).apply(lambda_func)
        assert isinstance(result, AsyncResult)
        pytest.raises(RuntimeError, result.result)

    def test_terminator(self):
        def temp_func() -> None:
            import time

            time.sleep(1)

        result = self.executor(0.5).apply(temp_func)
        assert isinstance(result, AsyncResult)
        pytest.raises(TimeoutError, result.result)

        assert result._terminator.is_active is True  # noqa: SLF001

    def test_awaitable_non_coroutine(self):
        if self.use_jinja:
            pytest.skip("TODO: not yet tested with JinjaExecutor")

        expect = "done"

        def awaitable_func() -> Awaitable[Any]:
            return self.awaitable(value=expect)

        result = self.executor(1).apply(awaitable_func)
        assert isinstance(result, AsyncResult)
        result = result.result()
        assert isinstance(result, str)
        assert result == expect


class TestExecutorAsync(BaseExecutorTest):
    @pytest.mark.parametrize(
        ("x", "y"), list(product(range(TEST_SIZE), range(TEST_SIZE)))
    )
    async def test_apply_args(self, x: int, y: int):
        result = await self.executor(1).delay(self.sample_async_func, x, y)
        assert isinstance(result, AsyncResult)
        result = await result.delay()
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert not result[1]
        assert isinstance(result[0], tuple)
        assert result[0] == (x, y)

    @pytest.mark.parametrize(
        ("x", "y"), list(product(range(TEST_SIZE), range(TEST_SIZE)))
    )
    async def test_apply_kwargs(self, *, x: int, y: int):
        result = await self.executor(1).delay(self.sample_async_func, x=x, y=y)
        assert isinstance(result, AsyncResult)
        result = await result.delay()
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert not result[0]
        assert isinstance(result[1], dict)
        assert result[1] == {"x": x, "y": y}

    async def test_apply_timeout(self):
        async def sleep(x: float) -> None:
            import anyio

            await anyio.sleep(x)

        result = await self.executor(1).delay(sleep, 1.5)
        with pytest.raises(TimeoutError):
            await result.delay(0.1)

    @pytest.mark.parametrize("x", range(TEST_SIZE))
    async def test_apply_lambda(self, x: int):
        async def lambdalike(x: int) -> int:
            import anyio

            await anyio.sleep(0.1)
            return x

        result = await self.executor(1).delay(lambdalike, x)
        assert isinstance(result, AsyncResult)
        result = await result.delay()
        assert isinstance(result, int)
        assert result == x

    async def test_apply_lambda_error(self):
        async def lambdalike() -> int:
            import anyio

            await anyio.sleep(10)
            raise RuntimeError("error")

        result = await self.executor(1).delay(lambdalike)
        with pytest.raises(TimeoutError):
            await result.delay(0.1)

    async def test_terminator(self):
        async def temp_func() -> None:
            import anyio

            await anyio.sleep(1)

        result = await self.executor(0.5).delay(temp_func)
        assert isinstance(result, AsyncResult)
        with pytest.raises(TimeoutError):
            await result.delay()

        assert result._terminator.is_active is True  # noqa: SLF001

    async def test_awaitable_non_coroutine(self):
        if self.use_jinja:
            pytest.skip("TODO: not yet tested with JinjaExecutor")

        expect = "done"

        def awaitable_func() -> Awaitable[Any]:
            return self.awaitable(value=expect)

        result = await self.executor(1).delay(awaitable_func)
        assert isinstance(result, AsyncResult)
        result = await result.delay()
        assert isinstance(result, str)
        assert result == expect


class TestJinjaExecutorSync(TestExecutorSync):
    use_jinja = True

    def test_lambda_error(self):
        lambda_func = lambda: 123  # noqa: E731
        with pytest.raises(ValueError, match="lambda function is not supported"):
            self.executor(1).apply(lambda_func)


class TestJinjaExecutorAsync(TestExecutorAsync):
    use_jinja = True


def test_environment_variable():
    key, value = "E" + uuid.uuid4().hex.upper(), str(uuid.uuid4())
    os.environ[key] = value

    def func() -> bool:
        import os

        return os.environ.get(key) == value

    result = TimeoutExecutor(1).apply(func)
    assert result.result() is True
