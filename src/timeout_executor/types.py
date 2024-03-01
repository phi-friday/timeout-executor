from __future__ import annotations

import sys
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Iterable

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


@dataclass(frozen=True)
class ExecutorArgs:
    """executor args"""

    executor: Executor
    func_name: str
    terminator: Terminator
    input_file: Path | anyio.Path
    output_file: Path | anyio.Path
    timeout: float


@dataclass
class State:
    value: Any = field(default=None)


@dataclass(frozen=True)
class CallbackArgs:
    """callback args"""

    process: subprocess.Popen[str]
    result: AsyncResult
    state: State = field(default_factory=State)


class Callback(ABC):
    """callback api interface"""

    @abstractmethod
    def callbacks(self) -> Iterable[ProcessCallback]:
        """return callbacks"""

    @abstractmethod
    def add_callback(self, callback: ProcessCallback) -> Self:
        """add callback"""

    @abstractmethod
    def remove_callback(self, callback: ProcessCallback) -> Self:
        """remove callback if exists"""

    def run_callbacks(self, callback_args: CallbackArgs, func_name: str) -> None:
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


ProcessCallback: TypeAlias = "Callable[[CallbackArgs], Any]"
