from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Literal

from timeout_executor.log import logger

if TYPE_CHECKING:
    from timeout_executor.concurrent.main import ContextType
    from timeout_executor.pickler.base import ContextModule, PicklerModule

__all__ = ["monkey_patch"]

PicklerType = Literal["pickle", "dill", "cloudpickle"]


def monkey_patch(context: ContextType, pickler: PicklerType | None) -> None:
    """monkey patch or unpatch"""
    context_module = _import_context(context)
    pickler = _validate_pickler(context_module, pickler)
    if pickler in context_module.unpatch:
        logger.info("context: %r: unpatch", context)
        context_module.monkey_unpatch()
        return
    pickler_module = _import_pickler(pickler)
    logger.info("context: %r, pickler: %r: patch", context, pickler)
    context_module.monkey_patch(pickler, pickler_module.Pickler)


def _import_context(context: ContextType) -> ContextModule:
    return importlib.import_module(f"._{context}", __package__)  # type: ignore


def _import_pickler(pickler: PicklerType) -> PicklerModule:
    return importlib.import_module(f"._{pickler}", __package__)  # type: ignore


def _validate_pickler(
    context: ContextModule,
    pickler: PicklerType | None,
) -> PicklerType:
    pickler = pickler or context.order[0]
    if pickler in context.replace:
        pickler = context.replace[pickler]
    return pickler
