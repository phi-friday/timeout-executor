from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from timeout_executor.pickler.base import Pickler

__all__ = ["monkey_patch", "monkey_unpatch"]


def monkey_patch(name: str, pickler: Pickler) -> None:  # noqa: ARG001
    """dummy patch joblib"""


def monkey_unpatch() -> None:
    """dummy unpatch joblib"""
