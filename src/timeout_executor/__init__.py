from __future__ import annotations

from typing import Any

from timeout_executor.process import TimeoutExecutor, delay_func, execute_func

__all__ = ["TimeoutExecutor", "execute_func", "delay_func"]

__version__: str


def __getattr__(name: str) -> Any:  # pragma: no cover
    from importlib.metadata import version

    if name == "__version__":
        return version("timeout-executor")

    error_msg = f"The attribute named {name!r} is undefined."
    raise AttributeError(error_msg)
