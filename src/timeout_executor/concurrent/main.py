from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Literal, overload

if TYPE_CHECKING:
    from .futures import _billiard as billiard_future
    from .futures import _loky as loky_future
    from .futures import _multiprocessing as multiprocessing_future

__all__ = ["get_context_executor"]

ContextType = Literal["billiard", "multiprocessing", "loky"]
DEFAULT_CONTEXT = "multiprocessing"


@overload
def get_context_executor(
    context: Literal["multiprocessing"] | None = ...,
) -> type[multiprocessing_future.ProcessPoolExecutor]:
    ...


@overload
def get_context_executor(
    context: Literal["billiard"] = ...,
) -> type[billiard_future.ProcessPoolExecutor]:
    ...


@overload
def get_context_executor(
    context: Literal["loky"] = ...,
) -> type[loky_future.ProcessPoolExecutor]:
    ...


@overload
def get_context_executor(
    context: str = ...,
) -> (
    type[billiard_future.ProcessPoolExecutor]
    | type[multiprocessing_future.ProcessPoolExecutor]
    | type[loky_future.ProcessPoolExecutor]
):
    ...


def get_context_executor(
    context: ContextType | str | None = None,
) -> (
    type[billiard_future.ProcessPoolExecutor]
    | type[multiprocessing_future.ProcessPoolExecutor]
    | type[loky_future.ProcessPoolExecutor]
):
    """get pool executor

    Args:
        context: billiard or multiprocessing or loky.
            Defaults to None.

    Returns:
        ProcessPoolExecutor
    """
    if not context:
        context = DEFAULT_CONTEXT

    module = importlib.import_module(f".futures._{context}", __package__)
    return module.ProcessPoolExecutor
