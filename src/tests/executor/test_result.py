from __future__ import annotations

from collections.abc import Awaitable

import pytest

from tests.executor.base import BaseExecutorTest

pytestmark = pytest.mark.anyio


class TestExecutorSync(BaseExecutorTest):
    def test_wait(self):
        result = self.executor(1).apply(self.sample_func, 1, 1)
        assert not result.has_result
        wait_value = result.wait(do_async=False)
        assert wait_value is None
        assert not result.has_result
        result.result()
        assert result.has_result

    def test_wait_timeout(self):
        def func() -> None:
            import time

            time.sleep(10)

        result = self.executor(10).apply(func)
        with pytest.raises(TimeoutError):
            result.wait(timeout=1, do_async=False)


class TestExecutorAsync(BaseExecutorTest):
    async def test_wait(self):
        result = self.executor(1).apply(self.sample_func, 1, 1)
        assert not result.has_result
        wait_value = result.wait()
        assert wait_value is not None
        assert isinstance(wait_value, Awaitable)
        await wait_value
        assert not result.has_result
        await result.delay()
        assert result.has_result

    async def test_wait_timeout(self):
        async def func() -> None:
            import anyio

            await anyio.sleep(10)

        result = self.executor(10).apply(func)
        with pytest.raises(TimeoutError):
            await result.wait(timeout=1)
