from __future__ import annotations

from typing import Any, Generic, NoReturn, TypeVar, final

ValueT = TypeVar("ValueT")

__all__ = ["ReadOnly"]


@final
class ReadOnly(Generic[ValueT]):
    def __init__(self, value: ValueT) -> None:
        self._value = value

    @property
    def value(self) -> ValueT:  # noqa: D102
        return self._value

    @value.setter
    def value(self, value: Any) -> NoReturn:
        raise NotImplementedError

    @value.deleter
    def value(self) -> NoReturn:
        raise NotImplementedError

    def __eq__(self, value: Any) -> bool:
        return type(value) is type(self.value) and value == self.value  # noqa: E721

    def force_set(self, value: ValueT) -> None:  # noqa: D102
        self._value = value
