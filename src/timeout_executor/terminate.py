from __future__ import annotations

import subprocess
import sys
import threading
from collections import deque
from contextlib import suppress
from itertools import chain
from typing import TYPE_CHECKING, Any, Callable, Generic

from psutil import pid_exists
from typing_extensions import ParamSpec, Self, TypeVar, override

from timeout_executor.logging import logger
from timeout_executor.types import Callback, CallbackArgs, ExecutorArgs, ProcessCallback

if TYPE_CHECKING:
    from collections.abc import Iterable

__all__ = []

P = ParamSpec("P")
T = TypeVar("T", infer_variance=True)


class Terminator(Callback[P, T], Generic[P, T]):
    """process terminator.

    run callbacks and terminate process.
    """

    __slots__ = (
        "_is_active",
        "_executor_args",
        "_init_callbacks",
        "_callbacks",
        "_callback_args",
        "_callback_thread",
        "_terminator_thread",
    )

    _process: subprocess.Popen[str] | None
    _callback_thread: threading.Thread | None
    _terminator_thread: threading.Thread | None

    def __init__(
        self,
        executor_args_factory: Callable[[Terminator[P, T]], ExecutorArgs[P, T]],
        callbacks: Callable[[], Iterable[ProcessCallback[P, T]]] | None = None,
    ) -> None:
        self._is_active = False
        self._executor_args = executor_args_factory(self)
        self._init_callbacks = callbacks
        self._callbacks: deque[ProcessCallback[P, T]] = deque()

        self._callback_thread = None
        self._terminator_thread = None

        self._callback_args: CallbackArgs[P, T] | None = None

    @property
    def executor_args(self) -> ExecutorArgs[P, T]:
        return self._executor_args

    @property
    def callback_args(self) -> CallbackArgs[P, T]:
        """callback args.

        will be set in executor.
        """
        if self._callback_args is None:
            raise AttributeError("there is no callback args")
        return self._callback_args

    @callback_args.setter
    def callback_args(self, value: CallbackArgs[P, T]) -> None:
        if self._callback_args is not None:
            raise AttributeError("already has callback args")
        self._callback_args = value

    @property
    def callback_thread(self) -> threading.Thread:
        """callback thread.

        will be set in start method.
        """
        if self._callback_thread is None:
            raise AttributeError("there is no callback thread")
        return self._callback_thread

    @property
    def terminator_thread(self) -> threading.Thread:
        """terminator thread.

        will be set in start method.
        """
        if self._terminator_thread is None:
            raise AttributeError("there is no terminator thread")
        return self._terminator_thread

    @property
    def timeout(self) -> float:
        return self._executor_args.timeout

    @property
    def is_active(self) -> bool:
        """process is terminated or not."""
        return self._is_active

    def start(self) -> None:
        """watch process and run callbacks."""
        if self._terminator_thread is not None or self._callback_thread is not None:
            raise PermissionError("already started")
        self._start_callback_thread()
        self._start_terminator_thread()

    def _start_terminator_thread(self) -> None:
        logger.debug("%r create terminator thread", self)
        self._terminator_thread = threading.Thread(
            target=terminate,
            args=(self,),
            name=f"{self.func_name}-callback-{self.executor_args.executor.unique_id}",
        )
        self._terminator_thread.daemon = True
        self._terminator_thread.start()
        logger.debug(
            "%r terminator thread: %d", self, self._terminator_thread.ident or -1
        )

    def _start_callback_thread(self) -> None:
        logger.debug("%r create callback thread", self)
        self._callback_thread = threading.Thread(
            target=callback,
            args=(self,),
            name=f"{self.func_name}-terminator-{self.executor_args.executor.unique_id}",
        )
        self._callback_thread.daemon = True
        self._callback_thread.start()
        logger.debug("%r callback thread: %d", self, self._callback_thread.ident or -1)

    def close(self, name: str | None = None) -> None:
        """run callbacks and terminate process."""
        logger.debug("%r try to terminate process from %s", self, name or "unknown")
        process = self.callback_args.process
        if process.returncode is None:
            if pid_exists(process.pid):
                try:
                    process.terminate()
                except ProcessLookupError:
                    logger.warning(
                        "%r process has no return code "
                        "but cant find process :: pid: %d",
                        self,
                        process.pid,
                    )
                else:
                    self._is_active = True
            else:
                logger.warning(
                    "%r process has no return code but cant find process :: pid: %d",
                    self,
                    process.pid,
                )

        if process.stdout is not None:
            text = process.stdout.read()
            if text:
                sys.stdout.write(text)
        if process.stderr is not None:
            text = process.stderr.read()
            if text:
                sys.stderr.write(text)

    @override
    def __repr__(self) -> str:
        return f"<{type(self).__name__}: {self.func_name}>"

    @property
    def func_name(self) -> str:
        return self._executor_args.func_name

    @override
    def callbacks(self) -> Iterable[ProcessCallback[P, T]]:
        if self._init_callbacks is None:
            return self._callbacks.copy()
        return chain(self._init_callbacks(), self._callbacks.copy())

    @override
    def add_callback(self, callback: ProcessCallback[P, T]) -> Self:
        if (
            self.is_active
            or self.callback_args.process.returncode is not None
            or not self.callback_thread.is_alive()
        ):
            logger.warning("%r already ended -> skip add callback %r", self, callback)
            return self
        self._callbacks.append(callback)
        return self

    @override
    def remove_callback(self, callback: ProcessCallback[P, T]) -> Self:
        with suppress(ValueError):
            self._callbacks.remove(callback)
        return self


def terminate(terminator: Terminator[Any, Any]) -> None:
    try:
        with suppress(TimeoutError, subprocess.TimeoutExpired):
            terminator.callback_args.process.wait(terminator.timeout)
    finally:
        terminator.close("terminator thread")


def callback(terminator: Terminator[Any, Any]) -> None:
    try:
        terminator.callback_args.process.wait()
    finally:
        terminator.run_callbacks(terminator.callback_args, terminator.func_name)
