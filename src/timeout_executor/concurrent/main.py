from __future__ import annotations

from importlib import import_module
from importlib.util import find_spec
from typing import TYPE_CHECKING, Literal, overload

if TYPE_CHECKING:
    from .futures.backend import _billiard as billiard_future
    from .futures.backend import _loky as loky_future
    from .futures.backend import _multiprocessing as multiprocessing_future

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
    name = f".futures.backend._{backend}"
    spec = find_spec(name, __package__)
    if spec is None:
        error_msg = f"invalid backend: {backend}"
        raise ImportError(error_msg)
    module = import_module(name, __package__)
    return module.ProcessPoolExecutor
