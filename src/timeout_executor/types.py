from __future__ import annotations

import sys
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Generic, Iterable

from typing_extensions import ParamSpec, TypeVar

from timeout_executor.logging import logger

if sys.version_info < (3, 11):
    from exceptiongroup import ExceptionGroup  # type: ignore

if TYPE_CHECKING:
    import subprocess
    from pathlib import Path

    import anyio
    from typing_extensions import Self, TypeAlias

    from timeout_executor.executor import Executor
    from timeout_executor.result import AsyncResult
    from timeout_executor.terminate import Terminator


__all__ = ["ExecutorArgs", "CallbackArgs", "ProcessCallback", "Callback"]

_DATACLASS_FROZEN_KWARGS: dict[str, bool] = {"frozen": True}
_DATACLASS_NON_FROZEN_KWARGS: dict[str, bool] = {}
if sys.version_info >= (3, 10):
    _DATACLASS_FROZEN_KWARGS.update({"kw_only": True, "slots": True})
    _DATACLASS_NON_FROZEN_KWARGS.update({"kw_only": True, "slots": True})

P = ParamSpec("P")
T = TypeVar("T", infer_variance=True)


@dataclass(**_DATACLASS_FROZEN_KWARGS)
class ExecutorArgs(Generic[P, T]):
    """executor args"""

    executor: Executor[P, T]
    func_name: str
    terminator: Terminator[P, T]
    input_file: Path | anyio.Path
    output_file: Path | anyio.Path
    timeout: float


@dataclass(**_DATACLASS_NON_FROZEN_KWARGS)
class State:
    value: Any = field(default=None)


@dataclass(**_DATACLASS_FROZEN_KWARGS)
class CallbackArgs(Generic[P, T]):
    """callback args"""

    process: subprocess.Popen[str]
    result: AsyncResult[P, T]
    state: State = field(init=False, default_factory=State)


class Callback(ABC, Generic[P, T]):
    """callback api interface"""

    @abstractmethod
    def callbacks(self) -> Iterable[ProcessCallback[P, T]]:
        """return callbacks"""

    @abstractmethod
    def add_callback(self, callback: ProcessCallback[P, T]) -> Self:
        """add callback"""

    @abstractmethod
    def remove_callback(self, callback: ProcessCallback[P, T]) -> Self:
        """remove callback if exists"""

    def run_callbacks(self, callback_args: CallbackArgs[P, T], func_name: str) -> None:
        """run all callbacks"""
        logger.debug("%r start callbacks", self)
        errors: deque[Exception] = deque()
        for callback in self.callbacks():
            try:
                callback(callback_args)
            except Exception as exc:  # noqa: PERF203, BLE001
                errors.append(exc)
                continue

        logger.debug("%r end callbacks", self)
        if errors:
            error_msg = f"[{func_name}] error when run callback"
            raise ExceptionGroup(error_msg, errors)


ProcessCallback: TypeAlias = "Callable[[CallbackArgs[P, T]], Any]"
