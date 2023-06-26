from __future__ import annotations

import copyreg
import io
from typing import Any, Callable, ClassVar, TypeVar

from timeout_executor.exception import ExtraError

try:
    import cloudpickle  # type: ignore
except ImportError as exc:
    error = ExtraError.from_import_error(exc, extra="cloudpickle")
    raise error from exc

ValueT = TypeVar("ValueT")

__all__ = ["Pickler"]


class Pickler(cloudpickle.Pickler):
    _extra_reducers: ClassVar[dict[type[Any], Callable[[Any], Any]]] = {}
    _copyreg_dispatch_table = copyreg.dispatch_table

    def __init__(self, *args: Any) -> None:
        super().__init__(*args)
        self.dispatch_table = self._copyreg_dispatch_table.copy()
        self.dispatch_table.update(self._extra_reducers)

    @classmethod
    def register(
        cls,
        type: type[ValueT],  # noqa: A002
        reduce: Callable[[ValueT], Any],
    ) -> None:
        """Register a reduce function for a type."""
        cls._extra_reducers[type] = reduce

    @classmethod
    def dumps(
        cls,
        obj: Any,
        protocol: int | None = None,
    ) -> memoryview:
        buf = io.BytesIO()
        cls(buf, protocol).dump(obj)
        return buf.getbuffer()

    @classmethod
    def loadbuf(
        cls,
        buf: io.BytesIO,
        protocol: int | None = None,  # noqa: ARG003
    ) -> Any:
        return cls.loads(buf.getbuffer())  # type: ignore

    loads = cloudpickle.loads
