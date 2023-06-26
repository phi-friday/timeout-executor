from __future__ import annotations

from typing import TYPE_CHECKING

from timeout_executor.log import logger

if TYPE_CHECKING:
    from timeout_executor.pickler.base import Pickler

__all__ = ["monkey_patch", "monkey_unpatch"]


def monkey_patch(name: str, pickler: Pickler) -> None:  # noqa: ARG001
    """patch loky"""
    if name == "pickle":
        logger.warning("loky uses cloudpickle as the default")
        name = "cloudpickle"
    try:
        from loky.backend.reduction import (  # type: ignore
            get_loky_pickler_name,  # type: ignore
            set_loky_pickler,  # type: ignore
        )
    except (ImportError, ModuleNotFoundError) as exc:
        raise ImportError("install extra first: loky") from exc

    if get_loky_pickler_name() == name:
        return
    set_loky_pickler(name)


def monkey_unpatch() -> None:
    """unpatch loky"""
    try:
        from loky.backend.reduction import (  # type: ignore
            get_loky_pickler_name,  # type: ignore
            set_loky_pickler,  # type: ignore
        )
    except (ImportError, ModuleNotFoundError) as exc:
        raise ImportError("install extra first: loky") from exc

    if get_loky_pickler_name == "cloudpickle":
        return
    set_loky_pickler()
