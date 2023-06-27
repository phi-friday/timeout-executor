from __future__ import annotations

from typing import TYPE_CHECKING

from timeout_executor.exception import ExtraError
from timeout_executor.log import logger

if TYPE_CHECKING:
    from timeout_executor.pickler.base import Pickler
    from timeout_executor.pickler.main import PicklerType

__all__ = ["monkey_patch", "monkey_unpatch"]

default: PicklerType = "cloudpickle"
order: tuple[PicklerType, ...] = ("cloudpickle", "dill")


def monkey_patch(name: str, pickler: type[Pickler]) -> None:  # noqa: ARG001
    """patch loky"""
    from timeout_executor.pickler.lock import patch_lock

    with patch_lock:
        if name == "pickle":
            logger.warning("loky uses cloudpickle as the default")
            name = "cloudpickle"
        try:
            from loky.backend.reduction import (  # type: ignore
                get_loky_pickler_name,  # type: ignore
                set_loky_pickler,  # type: ignore
            )
        except ImportError as exc:
            error = ExtraError.from_import_error(exc, extra="loky")
            raise error from exc

        if get_loky_pickler_name() == name:
            return
        set_loky_pickler(name)


def monkey_unpatch() -> None:
    """unpatch loky"""
    from timeout_executor.pickler.lock import patch_lock

    with patch_lock:
        try:
            from loky.backend.reduction import (  # type: ignore
                get_loky_pickler_name,  # type: ignore
                set_loky_pickler,  # type: ignore
            )
        except ImportError as exc:
            error = ExtraError.from_import_error(exc, extra="loky")
            raise error from exc

        if get_loky_pickler_name == "cloudpickle":
            return
        set_loky_pickler()
