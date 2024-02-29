from __future__ import annotations

import subprocess
import sys
import threading
from contextlib import suppress

__all__ = []


class Terminator:
    _process: subprocess.Popen[str] | None

    def __init__(self, timeout: float) -> None:
        self._process = None
        self._timeout = timeout
        self._is_active = False

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
        self.thread = threading.Thread(
            target=terminate, args=(self._timeout, self.process, self)
        )
        self.thread.daemon = True
        self.thread.start()

    def close(self) -> None:
        if self.process.returncode is None:
            self.process.terminate()
            self.is_active = True

        if self.process.stdout is not None:
            text = self.process.stdout.read()
            sys.stdout.write(text)
        if self.process.stderr is not None:
            text = self.process.stderr.read()
            sys.stderr.write(text)


def terminate(
    timeout: float, process: subprocess.Popen, terminator: Terminator
) -> None:
    try:
        with suppress(TimeoutError, subprocess.TimeoutExpired):
            process.wait(timeout)
    finally:
        terminator.close()
