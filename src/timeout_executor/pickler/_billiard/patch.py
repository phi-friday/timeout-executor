from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Final

from timeout_executor.exception import ExtraError
from timeout_executor.readonly import ReadOnly

if TYPE_CHECKING:
    from timeout_executor.pickler.base import Pickler

__all__ = ["monkey_patch", "monkey_unpatch"]

billiard_origin: ReadOnly[type[Pickler]] = ReadOnly(None)  # type: ignore
billiard_origin_status: Final[str] = "billiard"
billiard_status: ReadOnly[str] = ReadOnly(billiard_origin_status)


def monkey_patch(name: str, pickler: Pickler) -> None:
    """patch billiard"""
    from timeout_executor.pickler.lock import patch_lock

    with patch_lock:
        if billiard_status == name:
            return

        _set_origin()
        try:
            from billiard import (  # type: ignore
                connection,  # type: ignore
                queues,  # type: ignore
                reduction,  # type: ignore
                sharedctypes,  # type: ignore
            )
        except ImportError as exc:
            error = ExtraError.from_import_error(exc, extra="billiard")
            raise error from exc

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

        billiard_status.force_set(name)


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
        except ImportError as exc:
            error = ExtraError.from_import_error(exc, extra="billiard")
            raise error from exc

        if billiard_status == billiard_origin_status:
            return
        if billiard_origin.value is None:
            raise RuntimeError("origin is None")

        reduction.ForkingPickler = billiard_origin.value
        reduction.register = billiard_origin.value.register
        queues.ForkingPickler = billiard_origin.value
        connection.ForkingPickler = billiard_origin.value
        sharedctypes.ForkingPickler = billiard_origin.value

        billiard_status.force_set(billiard_origin_status)


def _set_origin() -> None:
    if billiard_origin.value is not None:
        return

    try:
        from billiard.reduction import ForkingPickler
    except ImportError as exc:
        error = ExtraError.from_import_error(exc, extra="billiard")
        raise error from exc

    billiard_origin.force_set(ForkingPickler)  # type: ignore
