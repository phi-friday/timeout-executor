from __future__ import annotations

import sys
from textwrap import indent
from typing import TYPE_CHECKING, Any, Sequence

from typing_extensions import Self, override

if sys.version_info < (3, 11):
    from exceptiongroup import ExceptionGroup  # type: ignore

__all__ = ["ExtraError", "ImportErrors"]


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


class ImportErrors(ExceptionGroup[ImportError]):
    if TYPE_CHECKING:

        @override
        def __new__(cls, __message: str, __exceptions: Sequence[ImportError]) -> Self:
            ...

        exceptions: Sequence[ImportError]

    def render(self, depth: int = 0) -> str:  # noqa: D102
        msg = str(self)
        if depth:
            msg = indent(msg, prefix="    ")
        return msg

    def __str__(self) -> str:
        return (
            super().__str__()
            + "\n"
            + indent(
                "\n".join(f"[{error.name}] {error!s}" for error in self.exceptions),
                prefix="    ",
            )
        )
