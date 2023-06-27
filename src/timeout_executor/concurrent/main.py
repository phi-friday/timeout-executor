from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Literal, overload

if TYPE_CHECKING:
    from .futures import _billiard as billiard_future
    from .futures import _loky as loky_future
    from .futures import _multiprocessing as multiprocessing_future

__all__ = ["get_executor_backend"]

BackendType = Literal["billiard", "multiprocessing", "loky"]
DEFAULT_BACKEND = "multiprocessing"


@overload
def get_executor_backend(
    backend: Literal["multiprocessing"] | None = ...,
) -> type[multiprocessing_future.ProcessPoolExecutor]:
    ...


@overload
def get_executor_backend(
    backend: Literal["billiard"] = ...,
) -> type[billiard_future.ProcessPoolExecutor]:
    ...


@overload
def get_executor_backend(
    backend: Literal["loky"] = ...,
) -> type[loky_future.ProcessPoolExecutor]:
    ...


def get_executor_backend(
    backend: BackendType | None = None,
) -> (
    type[billiard_future.ProcessPoolExecutor]
    | type[multiprocessing_future.ProcessPoolExecutor]
    | type[loky_future.ProcessPoolExecutor]
):
    """get pool executor

    Args:
        backend: billiard or multiprocessing or loky.
            Defaults to None.

    Returns:
        ProcessPoolExecutor
    """
    backend = backend or DEFAULT_BACKEND
    module = importlib.import_module(f".futures._{backend}", __package__)
    return module.ProcessPoolExecutor
