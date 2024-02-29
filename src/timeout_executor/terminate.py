from __future__ import annotations

import subprocess
import sys
import threading
from collections import deque
from contextlib import suppress
from itertools import chain
from typing import Any, Callable, Iterable

from typing_extensions import override

from timeout_executor.logging import logger
from timeout_executor.types import Callback, ExecutorArgs, ProcessCallback

__all__ = []


class Terminator(Callback):
    _process: subprocess.Popen[str] | None

    def __init__(
        self,
        executor_args: ExecutorArgs,
        callbacks: Callable[[], Iterable[ProcessCallback]] | None = None,
    ) -> None:
        self._process = None
        self._is_active = False
        self._executor_args = executor_args.copy({"terminator": self})
        self._init_callbacks = callbacks
        self._callbacks: deque[ProcessCallback] = deque()

    @property
    def process(self) -> subprocess.Popen[str]:
        if self._process is None:
            raise AttributeError("there is no process")
        return self._process

    @process.setter
    def process(self, process: subprocess.Popen[str]) -> None:
        if self._process is not None:
            raise AttributeError("already has process")
        self._process = process
        self._start()

    @property
    def timeout(self) -> float:
        return self._executor_args.timeout

    @property
    def is_active(self) -> bool:
        return self._is_active

    @is_active.setter
    def is_active(self, value: bool) -> None:
        self._is_active = value

    def _start(self) -> None:
        self._start_callback_thread()
        self._start_terminator_thread()

    def _start_terminator_thread(self) -> None:
        logger.debug("%r create terminator thread", self)
        self.terminator_thread = threading.Thread(
            target=terminate, args=(self.process, self)
        )
        self.terminator_thread.daemon = True
        self.terminator_thread.start()
        logger.debug(
            "%r terminator thread: %d", self, self.terminator_thread.ident or -1
        )

    def _start_callback_thread(self) -> None:
        logger.debug("%r create callback thread", self)
        self.callback_thread = threading.Thread(
            target=callback, args=(self.process, self)
        )
        self.callback_thread.daemon = True
        self.callback_thread.start()
        logger.debug("%r callback thread: %d", self, self.callback_thread.ident or -1)

    def close(self, name: str | None = None) -> None:
        logger.debug("%r try to terminate process from %s", self, name or "unknown")
        if self.process.returncode is None:
            self.process.terminate()
            self.is_active = True

        if self.process.stdout is not None:
            text = self.process.stdout.read()
            if text:
                sys.stdout.write(text)
        if self.process.stderr is not None:
            text = self.process.stderr.read()
            if text:
                sys.stderr.write(text)

    def __repr__(self) -> str:
        return f"<{type(self).__name__}: {self.func_name}>"

    @property
    def func_name(self) -> str:
        return self._executor_args.func_name

    @override
    def callbacks(self) -> Iterable[ProcessCallback]:
        if self._init_callbacks is None:
            return self._callbacks.copy()
        return chain(self._init_callbacks(), self._callbacks.copy())

    @override
    def add_callback(self, callback: Callable[[subprocess.Popen[str]], Any]) -> None:
        self._callbacks.append(callback)

    @override
    def remove_callback(self, callback: Callable[[subprocess.Popen[str]], Any]) -> None:
        with suppress(ValueError):
            self._callbacks.remove(callback)


def terminate(process: subprocess.Popen, terminator: Terminator) -> None:
    try:
        with suppress(TimeoutError, subprocess.TimeoutExpired):
            process.wait(terminator.timeout)
    finally:
        terminator.close("terminator thread")


def callback(process: subprocess.Popen, terminator: Terminator) -> None:
    process.wait()
    terminator.run_callbacks(process, terminator.func_name)
