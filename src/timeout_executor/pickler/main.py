from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Literal

from timeout_executor.log import logger

if TYPE_CHECKING:
    from timeout_executor.concurrent.main import BackendType
    from timeout_executor.pickler.base import BackendModule, PicklerModule

__all__ = ["monkey_patch"]

PicklerType = Literal["pickle", "dill", "cloudpickle"]


def monkey_patch(backend: BackendType, pickler: PicklerType | None) -> None:
    """monkey patch or unpatch"""
    backend_module = _import_backend(backend)
    pickler = _validate_pickler(backend, backend_module, pickler)
    if pickler in backend_module.unpatch:
        logger.debug("backend: %r, %r will be set to the default.", backend, pickler)
        logger.debug("backend: %r: unpatch", backend)
        backend_module.monkey_unpatch()
        return
    pickler_module = _import_pickler(pickler)
    logger.debug("backend: %r, pickler: %r: patch", backend, pickler)
    backend_module.monkey_patch(pickler, pickler_module.Pickler)


def _import_backend(backend: BackendType) -> BackendModule:
    return importlib.import_module(f"._{backend}", __package__)  # type: ignore


def _import_pickler(pickler: PicklerType) -> PicklerModule:
    return importlib.import_module(f"._{pickler}", __package__)  # type: ignore


def _validate_pickler(
    backend_name: BackendType,
    backend: BackendModule,
    pickler: PicklerType | None,
) -> PicklerType:
    if not pickler:
        logger.debug(
            "backend: %r, pickler is not specified. use default: %r.",
            backend_name,
            backend.order[0],
        )
        pickler = backend.order[0]
    if pickler in backend.replace:
        logger.debug(
            "backend: %r, %r is replaced by %r.",
            backend_name,
            pickler,
            backend.replace[pickler],
        )
        pickler = backend.replace[pickler]
    return pickler
