from __future__ import annotations

from typing import Any

from typing_extensions import Self, override

__all__ = ["ExtraError"]


class ExtraError(ImportError):
    @override
    def __init__(
        self,
        *args: Any,
        name: str | None = None,
        path: str | None = None,
        extra: str,
    ) -> None:
        super().__init__(*args, name=name, path=path)
        self._extra = extra

    @property
    @override
    def msg(self) -> str:
        return f"install extra first: {self._extra}"

    def __str__(self) -> str:
        return self.msg

    def __repr__(self) -> str:
        return f"{type(self).__name__!s}({self.msg!r})"

    @classmethod
    def from_import_error(cls, error: ImportError, extra: str) -> Self:
        """create from import error

        Args:
            error: import error
            extra: extra name

        Returns:
            extra error
        """
        return cls(name=error.name, path=error.path, extra=extra)
