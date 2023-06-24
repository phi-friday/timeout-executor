from __future__ import annotations

from typing import Any, Callable


def monkey_patch() -> None:
    """patch billiard as dill"""
    from multiprocessing import connection, queues, reduction, sharedctypes

    from timeout_executor.pickler.dill.base import ForkingPickler

    origin_register: dict[
        type[Any],
        Callable[[Any], Any],
    ] = reduction.ForkingPickler._extra_reducers  # noqa: SLF001 # type: ignore
    reduction.ForkingPickler = ForkingPickler
    reduction.register = ForkingPickler.register
    ForkingPickler._extra_reducers.update(origin_register)  # noqa: SLF001
    reduction.AbstractReducer.ForkingPickler = ForkingPickler  # type: ignore
    queues._ForkingPickler = ForkingPickler  # noqa: SLF001 # type: ignore
    connection._ForkingPickler = ForkingPickler  # noqa: SLF001 # type: ignore
    sharedctypes._ForkingPickler = ForkingPickler  # noqa: SLF001 # type: ignore
