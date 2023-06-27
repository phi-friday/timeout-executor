from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, ClassVar, Protocol, TypeVar

if TYPE_CHECKING:
    import io
    from types import ModuleType

    from timeout_executor.pickler.main import PicklerType

    class ContextModule(ModuleType):
        unpatch: frozenset[PicklerType]
        replace: dict[PicklerType, PicklerType]
        order: tuple[PicklerType]

        monkey_patch: Monkey
        monkey_unpatch: UnMonkey

    class PicklerModule(ModuleType):
        Pickler: Pickler


ValueT = TypeVar("ValueT")

__all__ = ["Pickler", "Monkey", "UnMonkey", "ContextModule", "PicklerModule"]


class Pickler(Protocol):
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
        cls,
        obj: Any,
        protocol: int | None = None,
    ) -> memoryview:
        ...

    @classmethod
    def loadbuf(  # noqa: D102
        cls,
        buf: io.BytesIO,
        protocol: int | None = None,
    ) -> Any:
        ...

    loads: Callable[..., Any]


Monkey = Callable[[str, Pickler], None]
UnMonkey = Callable[[], None]
