from __future__ import annotations

from typing import Any

from .executor import TimeoutExecutor, get_executor

__all__ = ["TimeoutExecutor", "get_executor"]

__version__: str


def __getattr__(name: str) -> Any:  # pragma: no cover
    from importlib.metadata import version

    if name == "__version__":
        return version("timeout-executor")

    error_msg = f"The attribute named {name!r} is undefined."
    raise AttributeError(error_msg)
