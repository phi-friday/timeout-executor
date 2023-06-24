from __future__ import annotations

from typing import Any, Callable

__all__ = ["monkey_patch", "monkey_unpatch"]

origin = None


def monkey_patch() -> None:
    """patch billiard as dill"""
    from timeout_executor.pickler.lock import patch_lock

    with patch_lock:
        from timeout_executor.pickler.cloudpickle.base import ForkingPickler

        try:
            from billiard import (  # type: ignore
                connection,  # type: ignore
                queues,  # type: ignore
                reduction,  # type: ignore
                sharedctypes,  # type: ignore
            )
        except (ImportError, ModuleNotFoundError) as exc:
            raise ImportError("install extra first: billiard") from exc

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
        queues.ForkingPickler = ForkingPickler
        connection.ForkingPickler = ForkingPickler
        sharedctypes.ForkingPickler = ForkingPickler


def monkey_unpatch() -> None:
    from timeout_executor.pickler.lock import patch_lock

    with patch_lock:
        try:
            from billiard import (  # type: ignore
                connection,  # type: ignore
                queues,  # type: ignore
                reduction,  # type: ignore
                sharedctypes,  # type: ignore
            )
        except (ImportError, ModuleNotFoundError) as exc:
            raise ImportError("install extra first: billiard") from exc

        global origin  # noqa: PLW0603
        if origin is None:
            return

        reduction.ForkingPickler = origin
        reduction.register = origin.register
        queues.ForkingPickler = origin
        connection.ForkingPickler = origin
        sharedctypes.ForkingPickler = origin

        origin = None
