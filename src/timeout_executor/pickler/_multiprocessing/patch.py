from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Final

from timeout_executor.readonly import ReadOnly

if TYPE_CHECKING:
    from timeout_executor.pickler.base import Pickler

__all__ = ["monkey_patch", "monkey_unpatch"]

multiprocessing_origin: ReadOnly[type[Pickler]] = ReadOnly(None)  # type: ignore
multiprocessing_origin_status: Final[str] = "multiprocessing"
multiprocessing_status: ReadOnly[str] = ReadOnly(multiprocessing_origin_status)


def monkey_patch(name: str, pickler: Pickler) -> None:
    """patch multiprocessing"""
    from timeout_executor.pickler.lock import patch_lock

    with patch_lock:
        if multiprocessing_status == name:
            return

        _set_origin()
        from multiprocessing import connection, queues, reduction, sharedctypes

        origin_register: dict[
            type[Any],
            Callable[[Any], Any],
        ] = reduction.ForkingPickler._extra_reducers  # noqa: SLF001 # type: ignore
        reduction.ForkingPickler = pickler
        reduction.register = pickler.register  # type: ignore
        pickler._extra_reducers.update(origin_register)  # noqa: SLF001
        reduction.AbstractReducer.ForkingPickler = pickler  # type: ignore
        queues._ForkingPickler = pickler  # noqa: SLF001 # type: ignore
        connection._ForkingPickler = pickler  # noqa: SLF001 # type: ignore
        sharedctypes._ForkingPickler = pickler  # noqa: SLF001 # type: ignore

        multiprocessing_status.force_set(name)


def monkey_unpatch() -> None:
    """unpatch multiprocessing"""
    from timeout_executor.pickler.lock import patch_lock

    with patch_lock:
        from multiprocessing import connection, queues, reduction, sharedctypes

        if multiprocessing_status == multiprocessing_origin_status:
            return
        if multiprocessing_origin.value is None:
            raise RuntimeError("origin is None")

        reduction.ForkingPickler = multiprocessing_origin.value
        reduction.register = multiprocessing_origin.value.register
        reduction.AbstractReducer.ForkingPickler = (  # type: ignore
            multiprocessing_origin.value
        )
        queues._ForkingPickler = (  # noqa: SLF001 # type: ignore
            multiprocessing_origin.value
        )
        connection._ForkingPickler = (  # noqa: SLF001  # type: ignore
            multiprocessing_origin.value
        )
        sharedctypes._ForkingPickler = (  # noqa: SLF001 # type: ignore
            multiprocessing_origin.value
        )

        multiprocessing_status.force_set(multiprocessing_origin_status)


def _set_origin() -> None:
    if multiprocessing_origin.value is not None:
        return

    from multiprocessing.reduction import ForkingPickler

    multiprocessing_origin.force_set(ForkingPickler)  # type: ignore
