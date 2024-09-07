from __future__ import annotations

from typing import Any

from timeout_executor.executor import apply_func, delay_func
from timeout_executor.main import TimeoutExecutor
from timeout_executor.result import AsyncResult

__all__ = ["TimeoutExecutor", "AsyncResult", "apply_func", "delay_func"]

__version__: str


def __getattr__(name: str) -> Any:  # pragma: no cover
    from importlib.metadata import version

    if name == "__version__":
        _version = version("timeout-executor")
        globals()["__version__"] = _version
        return _version

    error_msg = f"The attribute named {name!r} is undefined."
    raise AttributeError(error_msg)
