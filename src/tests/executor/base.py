from __future__ import annotations

from collections.abc import Awaitable
from typing import Any

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
