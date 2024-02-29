from __future__ import annotations

import subprocess
import sys
import threading
from contextlib import suppress

from timeout_executor.logging import logger

__all__ = []


class Terminator:
    _process: subprocess.Popen[str] | None

    def __init__(self, timeout: float, func_name: str) -> None:
        self._process = None
        self._timeout = timeout
        self._is_active = False
        self._func_name = func_name

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
    def is_active(self) -> bool:
        return self._is_active

    @is_active.setter
    def is_active(self, value: bool) -> None:
        self._is_active = value

    def _start(self) -> None:
        logger.debug("%r create terminator thread", self)
        self.thread = threading.Thread(
            target=terminate, args=(self._timeout, self.process, self)
        )
        self.thread.daemon = True
        self.thread.start()
        logger.debug("%r terminator thread: %d", self, self.thread.ident or -1)

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
        return f"<{type(self).__name__}: {self._func_name}>"


def terminate(
    timeout: float, process: subprocess.Popen, terminator: Terminator
) -> None:
    try:
        with suppress(TimeoutError, subprocess.TimeoutExpired):
            process.wait(timeout)
    finally:
        terminator.close("terminator thread")
