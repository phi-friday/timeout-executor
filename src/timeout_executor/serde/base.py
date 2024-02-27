from __future__ import annotations

from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    ClassVar,
    Protocol,
    Type,
    runtime_checkable,
)

from typing_extensions import TypeVar

if TYPE_CHECKING:
    import io
    from types import ModuleType

    from timeout_executor.serde.main import PicklerType

    class BackendModule(ModuleType):  # noqa: D101
        unpatch: frozenset[PicklerType]
        replace: dict[PicklerType, PicklerType]
        order: tuple[PicklerType]

        monkey_patch: Monkey
        monkey_unpatch: UnMonkey

    class PicklerModule(ModuleType):  # noqa: D101
        Pickler: type[Pickler]


ValueT = TypeVar("ValueT", infer_variance=True)

__all__ = ["Pickler", "Monkey", "UnMonkey", "BackendModule", "PicklerModule"]


@runtime_checkable
class Pickler(Protocol):  # noqa: D101
    _extra_reducers: ClassVar[dict[type[Any], Callable[[Any], Any]]]
    _copyreg_dispatch_table: ClassVar[dict[type[Any], Callable[[Any], Any]]]

    @classmethod
    def register(
        cls,
        type: type[ValueT],  # noqa: A002
        reduce: Callable[[ValueT], Any],
    ) -> None:
        """Register a reduce function for a type."""

    @classmethod
    def dumps(  # noqa: D102
        cls, obj: Any, protocol: int | None = None
    ) -> memoryview: ...

    @classmethod
    def loadbuf(  # noqa: D102
        cls, buf: io.BytesIO, protocol: int | None = None
    ) -> Any: ...

    loads: Callable[..., Any]


Monkey = Callable[[str, Type[Pickler]], None]
UnMonkey = Callable[[], None]
