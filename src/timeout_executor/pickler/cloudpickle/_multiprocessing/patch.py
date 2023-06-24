from __future__ import annotations

from typing import Any, Callable

__all__ = ["monkey_patch", "monkey_unpatch"]

origin = None


def monkey_patch() -> None:
    """patch billiard as dill"""
    from timeout_executor.pickler.lock import patch_lock

    with patch_lock:
        from multiprocessing import connection, queues, reduction, sharedctypes

        from timeout_executor.pickler.cloudpickle.base import ForkingPickler

        global origin  # noqa: PLW0603
        if origin is not None:
            return

        origin = reduction.ForkingPickler

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


def monkey_unpatch() -> None:
    from timeout_executor.pickler.lock import patch_lock

    with patch_lock:
        from multiprocessing import connection, queues, reduction, sharedctypes

        global origin  # noqa: PLW0603
        if origin is None:
            return

        reduction.ForkingPickler = origin
        reduction.register = origin.register
        reduction.AbstractReducer.ForkingPickler = origin  # type: ignore
        queues._ForkingPickler = origin  # noqa: SLF001 # type: ignore
        connection._ForkingPickler = origin  # noqa: SLF001 # type: ignore
        sharedctypes._ForkingPickler = origin  # noqa: SLF001 # type: ignore

        origin = None
