from __future__ import annotations

from ._version import __version__  # noqa: F401
from .executor import TimeoutExecutor, get_executor

__all__ = ["TimeoutExecutor", "get_executor"]
