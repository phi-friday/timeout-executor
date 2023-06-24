from __future__ import annotations

from typing import Any, Callable


def monkey_patch() -> None:
    """patch billiard as dill"""
    from timeout_executor.pickler.dill.base import ForkingPickler

    try:
        from billiard import connection, queues, reduction, sharedctypes  # type: ignore
    except (ImportError, ModuleNotFoundError) as exc:
        raise ImportError("install extra first: billiard") from exc

    origin_register: dict[
        type[Any],
        Callable[[Any], Any],
    ] = reduction.ForkingPickler._extra_reducers  # noqa: SLF001 # type: ignore
    reduction.ForkingPickler = ForkingPickler
    reduction.register = ForkingPickler.register
    ForkingPickler._extra_reducers.update(origin_register)  # noqa: SLF001
    queues.ForkingPickler = ForkingPickler
    connection.ForkingPickler = ForkingPickler
    sharedctypes.ForkingPickler = ForkingPickler
