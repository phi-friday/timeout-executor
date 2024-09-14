from __future__ import annotations

from collections.abc import Awaitable
from typing import Any

import anyio

from timeout_executor import TimeoutExecutor


class SomeAwaitable:
    def __init__(self, size: int = 5, value: Any = None) -> None:
        self.size = max(size, 5)
        self.value = value

    def __await__(self):  # noqa: ANN204
        for _ in range(self.size):
            yield None
        return "done"


class BaseExecutorTest:
    @staticmethod
    def executor(timeout: float) -> TimeoutExecutor[Any]:
        return TimeoutExecutor(timeout)

    @staticmethod
    def awaitable(size: int = 5, value: Any = None) -> Awaitable[Any]:
        return SomeAwaitable(size, value)

    @staticmethod
    def sample_func(
        *args: Any, **kwargs: Any
    ) -> tuple[tuple[Any, ...], dict[str, Any]]:
        return args, kwargs

    @staticmethod
    async def sample_async_func(
        *args: Any, **kwargs: Any
    ) -> tuple[tuple[Any, ...], dict[str, Any]]:
        await anyio.sleep(0.1)

        return BaseExecutorTest.sample_func(*args, **kwargs)
