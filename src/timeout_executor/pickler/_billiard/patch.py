from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Final

if TYPE_CHECKING:
    from timeout_executor.pickler.base import Pickler

__all__ = ["monkey_patch", "monkey_unpatch"]

billiard_origin: list[None | type[Pickler]] = [None]
billiard_origin_status: Final[str] = "billiard"
billiard_status = [billiard_origin_status]


def monkey_patch(name: str, pickler: Pickler) -> None:
    """patch billiard"""
    from timeout_executor.pickler.lock import patch_lock

    with patch_lock:
        if billiard_status[0] == name:
            return

        _set_origin()
        try:
            from billiard import (  # type: ignore
                connection,  # type: ignore
                queues,  # type: ignore
                reduction,  # type: ignore
                sharedctypes,  # type: ignore
            )
        except (ImportError, ModuleNotFoundError) as exc:
            raise ImportError("install extra first: billiard") from exc

        origin_register: dict[
            type[Any],
            Callable[[Any], Any],
        ] = reduction.ForkingPickler._extra_reducers  # noqa: SLF001 # type: ignore
        reduction.ForkingPickler = pickler
        reduction.register = pickler.register
        pickler._extra_reducers.update(origin_register)  # noqa: SLF001
        queues.ForkingPickler = pickler
        connection.ForkingPickler = pickler
        sharedctypes.ForkingPickler = pickler

        billiard_status[0] = name


def monkey_unpatch() -> None:
    """unpatch billiard"""
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

        if billiard_status == billiard_origin_status:
            return
        if billiard_origin[0] is None:
            raise RuntimeError("origin is None")

        reduction.ForkingPickler = billiard_origin[0]
        reduction.register = billiard_origin[0].register
        queues.ForkingPickler = billiard_origin[0]
        connection.ForkingPickler = billiard_origin[0]
        sharedctypes.ForkingPickler = billiard_origin[0]

        billiard_status[0] = billiard_origin_status


def _set_origin() -> None:
    if billiard_origin[0] is not None:
        return

    try:
        from billiard.reduction import ForkingPickler
    except (ImportError, ModuleNotFoundError) as exc:
        raise ImportError("install extra first: billiard") from exc

    billiard_origin[0] = ForkingPickler  # type: ignore
