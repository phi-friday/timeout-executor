from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Generic, TypeVar

from timeout_executor.exception import ExtraError

try:
    from loky.process_executor import (  # type: ignore
        ProcessPoolExecutor as LockyProcessPoolExecutor,  # type: ignore
    )
except ImportError as exc:
    error = ExtraError.from_import_error(exc, extra="loky")
    raise error from exc

__all__ = ["ProcessPoolExecutor"]


if TYPE_CHECKING:
    from multiprocessing.context import (
        DefaultContext,
        ForkContext,
        ForkServerContext,
        SpawnContext,
    )

    from loky._base import Future as LockyFuture  # type: ignore
    from typing_extensions import ParamSpec, override

    _P = ParamSpec("_P")
    _T = TypeVar("_T")

    class Future(LockyFuture, Generic[_T]):
        @override
        def add_done_callback(  # type: ignore
            self,
            fn: Callable[[Future[_T]], object],
        ) -> None:
            ...

        @override
        def set_result(self, result: _T) -> None:  # type: ignore
            ...

    class ProcessPoolExecutor(LockyProcessPoolExecutor):
        @override
        def __init__(  # noqa: PLR0913
            self,
            max_workers: int | None = None,
            job_reducers: dict[type[Any], Callable[[Any], Any]] | None = None,
            result_reducers: dict[type[Any], Callable[[Any], Any]] | None = None,
            timeout: float | None = None,
            context: ForkContext
            | SpawnContext
            | DefaultContext
            | ForkServerContext
            | None = None,
            initializer: Callable[[], Any] | None = None,
            initargs: tuple[Any, ...] = (),
            env: dict[str, Any] | None = None,
        ) -> None:
            ...

        @override
        def submit(  # type: ignore
            self,
            fn: Callable[_P, _T],
            /,
            *args: _P.args,
            **kwargs: _P.kwargs,
        ) -> Future[_T]:
            ...

        @override
        def shutdown(  # type: ignore
            self,
            wait: bool = True,  # noqa: FBT001
            kill_workers: bool = False,  # noqa: FBT001
        ) -> None:
            ...

else:
    ProcessPoolExecutor = LockyProcessPoolExecutor
