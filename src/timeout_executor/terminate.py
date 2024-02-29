from __future__ import annotations

import subprocess
import threading
from contextlib import suppress

__all__ = []


class Terminator:
    _process: subprocess.Popen | None

    def __init__(self, timeout: float) -> None:
        self._process = None
        self._timeout = timeout
        self._is_active = False

    @property
    def process(self) -> subprocess.Popen:
        if self._process is None:
            raise AttributeError("there is no process")
        return self._process

    @process.setter
    def process(self, process: subprocess.Popen) -> None:
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
        self.thread = threading.Thread(
            target=terminate, args=(self._timeout, self.process, self)
        )
        self.thread.daemon = True
        self.thread.start()


def terminate(
    timeout: float, process: subprocess.Popen, terminator: Terminator
) -> None:
    try:
        with suppress(TimeoutError, subprocess.TimeoutExpired):
            process.wait(timeout)
    finally:
        if process.returncode is None:
            process.terminate()
            terminator.is_active = True
