from __future__ import annotations

import sys
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Iterable, final

from timeout_executor.logging import logger

if sys.version_info < (3, 11):
    from exceptiongroup import ExceptionGroup  # type: ignore

if TYPE_CHECKING:
    import subprocess
    from pathlib import Path

    import anyio
    from typing_extensions import TypeAlias, TypedDict

    from timeout_executor.executor import Executor
    from timeout_executor.terminate import Terminator

    class ExecutorArgsUpdateDict(TypedDict, total=False):
        terminator: Terminator


__all__ = ["ExecutorArgs", "ProcessCallback", "Callback"]

ProcessCallback: TypeAlias = "Callable[[subprocess.Popen[str]], Any]"


@final
@dataclass(frozen=True)
class ExecutorArgs:
    """executor args"""

    executor: Executor
    func_name: str
    terminator: Terminator | None
    input_file: Path | anyio.Path
    output_file: Path | anyio.Path
    timeout: float

    def copy(self, update: ExecutorArgsUpdateDict | None = None) -> ExecutorArgs:
        """create new one"""
        update = update or {}
        return ExecutorArgs(
            executor=self.executor,
            func_name=self.func_name,
            terminator=update.get("terminator", self.terminator),
            input_file=self.input_file,
            output_file=self.output_file,
            timeout=self.timeout,
        )


class Callback(ABC):
    """callback api interface"""

    @abstractmethod
    def callbacks(self) -> Iterable[ProcessCallback]:
        """return callbacks"""

    @abstractmethod
    def add_callback(self, callback: ProcessCallback) -> None:
        """add callback"""

    @abstractmethod
    def remove_callback(self, callback: ProcessCallback) -> None:
        """remove callback if exists"""

    def run_callbacks(self, process: subprocess.Popen[str], func_name: str) -> None:
        """run all callbacks"""
        logger.debug("%r start callbacks", self)
        errors: deque[Exception] = deque()
        for callback in self.callbacks():
            try:
                callback(process)
            except Exception as exc:  # noqa: PERF203, BLE001
                errors.append(exc)
                continue

        logger.debug("%r end callbacks", self)
        if errors:
            error_msg = f"[{func_name}] error when run callback"
            raise ExceptionGroup(error_msg, errors)
