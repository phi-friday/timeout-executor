from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

from timeout_executor.log import logger

if TYPE_CHECKING:
    from timeout_executor.pickler.base import Monkey, Pickler, UnMonkey

__all__ = ["monkey_patch", "monkey_unpatch"]


def monkey_patch(context: str, pickler: str) -> None:
    """monkey patch"""
    context_module = importlib.import_module(f"._{context}", __package__)
    pickler_module = importlib.import_module(f"._{pickler}", __package__)
    pickler_class: Pickler = pickler_module.Pickler
    monkey_func: Monkey = context_module.monkey_patch
    logger.info("context: %r, pickler: %r: patch", context, pickler)
    monkey_func(pickler, pickler_class)


def monkey_unpatch(context: str) -> None:
    """monkey unpatch"""
    context_module = importlib.import_module(f"._{context}", __package__)
    unmonkey_func: UnMonkey = context_module.monkey_unpatch
    logger.info("context: %r: unpatch", context)
    unmonkey_func()
