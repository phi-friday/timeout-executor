"""obtained from concurrent.futures.process"""
from __future__ import annotations

import multiprocessing as mp
import os
import queue
import sys
import threading
import traceback
import weakref
from concurrent.futures import _base
from concurrent.futures.process import (
    _MAX_WINDOWS_WORKERS,
    EXTRA_QUEUED_CALLS,
    BrokenProcessPool,
    _CallItem,
    _chain_from_iterable_of_lists,
    _check_system_limits,
    _get_chunks,
    _global_shutdown,
    _process_chunk,
    _WorkItem,
)
from functools import partial
from multiprocessing import util as mp_util
from multiprocessing.connection import wait as mp_wait
from multiprocessing.queues import Queue
from traceback import format_exception
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Iterable,
    Iterator,
    TypeVar,
    Union,
)

from typing_extensions import ParamSpec, TypeAlias, override

if TYPE_CHECKING:
    from concurrent.futures import Future
    from multiprocessing.connection import Connection
    from multiprocessing.context import (
        DefaultContext,
        ForkContext,
        ForkServerContext,
        SpawnContext,
    )
    from multiprocessing.process import BaseProcess
    from multiprocessing.queues import SimpleQueue
    from threading import Lock
    from types import TracebackType

    Context: TypeAlias = Union[
        SpawnContext,
        ForkContext,
        ForkServerContext,
        DefaultContext,
    ]

    _P = ParamSpec("_P")
    _T = TypeVar("_T")


class _ThreadWakeup:
    _reader: Connection
    _writer: Connection

    def __init__(self) -> None:
        self._closed = False
        self._reader, self._writer = mp.Pipe(duplex=False)

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._writer.close()
            self._reader.close()

    def wakeup(self) -> None:
        if not self._closed:
            self._writer.send_bytes(b"")

    def clear(self) -> None:
        while self._reader.poll():
            self._reader.recv_bytes()


class _RemoteTraceback(Exception):  # noqa: N818
    def __init__(self, tb: str) -> None:
        self.tb = tb

    def __str__(self) -> str:
        return self.tb


class _ExceptionWithTraceback:
    def __init__(self, exc: BaseException, tb: TracebackType | None) -> None:
        tb_text = "".join(format_exception(type(exc), exc, tb))
        self.exc = exc
        # Traceback object needs to be garbage-collected as its frames
        # contain references to all the objects in the exception scope
        self.exc.__traceback__ = None
        self.tb = '\n"""\n%s"""' % tb_text

    def __reduce__(
        self,
    ) -> tuple[
        Callable[[BaseException, str], BaseException],
        tuple[BaseException, str],
    ]:
        return _rebuild_exc, (self.exc, self.tb)


class _ResultItem:
    def __init__(
        self,
        work_id: int,
        exception: Exception | _ExceptionWithTraceback | None = None,
        result: Any | None = None,
        exit_pid: int | None = None,
    ) -> None:
        self.work_id = work_id
        self.exception = exception
        self.result = result
        self.exit_pid = exit_pid


class _SafeQueue(Queue):
    """Safe Queue set exception to the future object linked to a job"""

    def __init__(  # noqa: PLR0913
        self,
        max_size: int = 0,
        *,
        ctx: Context,
        pending_work_items: dict[int, _WorkItem[Any]],
        shutdown_lock: Lock,
        thread_wakeup: _ThreadWakeup,
    ) -> None:
        self.pending_work_items = pending_work_items
        self.shutdown_lock = shutdown_lock
        self.thread_wakeup = thread_wakeup
        super().__init__(max_size, ctx=ctx)

    def _on_queue_feeder_error(self, e: Exception, obj: Any) -> None:
        if isinstance(obj, _CallItem):
            tb = traceback.format_exception(type(e), e, e.__traceback__)
            e.__cause__ = _RemoteTraceback('\n"""\n{}"""'.format("".join(tb)))
            work_item = self.pending_work_items.pop(obj.work_id, None)
            with self.shutdown_lock:
                self.thread_wakeup.wakeup()

            if work_item is not None:
                work_item.future.set_exception(e)
        else:
            self._mp_on_queue_feeder_error(e, obj)

    @staticmethod
    def _mp_on_queue_feeder_error(e: Any, obj: Any) -> None:  # noqa: ARG004
        import traceback

        traceback.print_exc()


class ProcessPoolExecutor(_base.Executor):
    """process pool executor"""

    _mp_context: Context

    def __init__(  # noqa: C901, PLR0912, PLR0913
        self,
        max_workers: int | None = None,
        mp_context: Context | None = None,
        initializer: Callable[..., Any] | None = None,
        initargs: tuple[Any, ...] = (),
        *,
        max_tasks_per_child: int | None = None,
    ) -> None:
        """Initializes a new ProcessPoolExecutor instance.

        Args:
            max_workers: The maximum number of processes that can be used to
                execute the given calls. If None or not given then as many
                worker processes will be created as the machine has processors.
            mp_context: A multiprocessing context to launch the workers. This
                object should provide SimpleQueue, Queue and Process. Useful
                to allow specific multiprocessing start methods.
            initializer: A callable used to initialize worker processes.
            initargs: A tuple of arguments to pass to the initializer.
            max_tasks_per_child: The maximum number of tasks a worker process
                can complete before it will exit and be replaced with a fresh
                worker process. The default of None means worker process will
                live as long as the executor. Requires a non-'fork' mp_context
                start method. When given, we default to using 'spawn' if no
                mp_context is supplied.
        """
        _check_system_limits()

        if max_workers is None:
            self._max_workers = os.cpu_count() or 1
            if sys.platform == "win32":
                self._max_workers = min(_MAX_WINDOWS_WORKERS, self._max_workers)
        else:
            if max_workers <= 0:
                raise ValueError("max_workers must be greater than 0")
            if sys.platform == "win32" and max_workers > _MAX_WINDOWS_WORKERS:
                error_msg = f"max_workers must be <= {_MAX_WINDOWS_WORKERS}"
                raise ValueError(error_msg)

            self._max_workers = max_workers

        if mp_context is None:
            if max_tasks_per_child is not None:
                self._mp_context = mp.get_context("spawn")
            elif (
                sys.platform == "linux"
                or sys.platform == "linux2"
                or sys.platform == "darwin"
            ):
                self._mp_context = mp.get_context("fork")
            else:
                self._mp_context = mp.get_context()
            mp_context = self._mp_context
        else:
            self._mp_context = mp_context

        self._safe_to_dynamically_spawn_children = (
            self._mp_context.get_start_method(allow_none=False) != "fork"
        )

        if initializer is not None and not callable(initializer):
            raise TypeError("initializer must be a callable")
        self._initializer = initializer
        self._initargs = initargs

        if max_tasks_per_child is not None:
            if not isinstance(max_tasks_per_child, int):
                raise TypeError("max_tasks_per_child must be an integer")
            if max_tasks_per_child <= 0:
                raise ValueError("max_tasks_per_child must be >= 1")
            if self._mp_context.get_start_method(allow_none=False) == "fork":
                raise ValueError(
                    "max_tasks_per_child is incompatible with"
                    " the 'fork' multiprocessing start method;"
                    " supply a different mp_context.",
                )
        self._max_tasks_per_child = max_tasks_per_child
        self._executor_manager_thread = None
        self._processes: dict[int | None, BaseProcess] = {}
        self._shutdown_thread = False
        self._shutdown_lock = threading.Lock()
        self._idle_worker_semaphore = threading.Semaphore(0)
        self._broken: str | bool = False
        self._queue_count = 0
        self._pending_work_items = {}
        self._cancel_pending_futures = False

        self._executor_manager_thread_wakeup: _ThreadWakeup = _ThreadWakeup()

        queue_size = self._max_workers + EXTRA_QUEUED_CALLS
        self._call_queue: _SafeQueue = _SafeQueue(
            max_size=queue_size,
            ctx=self._mp_context,
            pending_work_items=self._pending_work_items,
            shutdown_lock=self._shutdown_lock,
            thread_wakeup=self._executor_manager_thread_wakeup,
        )
        self._call_queue._ignore_epipe = True  # noqa: SLF001 # type: ignore
        self._result_queue: SimpleQueue = mp_context.SimpleQueue()
        self._work_ids = queue.Queue()

    def _start_executor_manager_thread(self) -> None:
        if self._executor_manager_thread is None:
            if not self._safe_to_dynamically_spawn_children:
                self._launch_processes()
            self._executor_manager_thread = _ExecutorManagerThread(self)
            self._executor_manager_thread.start()
            _threads_wakeups[
                self._executor_manager_thread
            ] = self._executor_manager_thread_wakeup

    def _adjust_process_count(self) -> None:
        if self._idle_worker_semaphore.acquire(blocking=False):
            return

        process_count = len(self._processes)
        if process_count < self._max_workers:
            self._spawn_process()

    def _launch_processes(self) -> None:
        # https://github.com/python/cpython/issues/90622
        assert not self._executor_manager_thread, (  # noqa: S101
            "Processes cannot be fork()ed after the thread has started, "
            "deadlock in the child processes could result."
        )
        for _ in range(len(self._processes), self._max_workers):
            self._spawn_process()

    def _spawn_process(self) -> None:
        p = self._mp_context.Process(
            target=_process_worker,
            args=(
                self._call_queue,
                self._result_queue,
                self._initializer,
                self._initargs,
                self._max_tasks_per_child,
            ),
        )
        p.start()
        self._processes[p.pid] = p

    @override
    def submit(
        self,
        fn: Callable[_P, _T],
        /,
        *args: _P.args,
        **kwargs: _P.kwargs,
    ) -> Future[_T]:
        with self._shutdown_lock:
            if self._broken:
                raise BrokenProcessPool(self._broken)
            if self._shutdown_thread:
                raise RuntimeError("cannot schedule new futures after shutdown")
            if _global_shutdown:
                raise RuntimeError(
                    "cannot schedule new futures after interpreter shutdown",
                )

            f = _base.Future()
            w = _WorkItem(f, fn, args, kwargs)

            self._pending_work_items[self._queue_count] = w
            self._work_ids.put(self._queue_count)
            self._queue_count += 1
            # Wake up queue management thread
            self._executor_manager_thread_wakeup.wakeup()

            if self._safe_to_dynamically_spawn_children:
                self._adjust_process_count()
            self._start_executor_manager_thread()
            return f

    @override
    def map(  # noqa: A003
        self,
        fn: Callable[..., _T],
        *iterables: Iterable[Any],
        timeout: float | None = None,
        chunksize: int = 1,
    ) -> Iterator[_T]:
        if chunksize < 1:
            raise ValueError("chunksize must be >= 1.")

        results = super().map(
            partial(_process_chunk, fn),
            _get_chunks(*iterables, chunksize=chunksize),
            timeout=timeout,
        )
        return _chain_from_iterable_of_lists(results)

    @override
    def shutdown(
        self,
        wait: bool = True,  # noqa: FBT001
        cancel_futures: bool = False,  # noqa: FBT001
    ) -> None:
        with self._shutdown_lock:
            self._cancel_pending_futures = cancel_futures
            self._shutdown_thread = True
            if self._executor_manager_thread_wakeup is not None:
                # Wake up queue management thread
                self._executor_manager_thread_wakeup.wakeup()

        if self._executor_manager_thread is not None and wait:
            self._executor_manager_thread.join()
        # To reduce the risk of opening too many files, remove references to
        # objects that use file descriptors.
        self._executor_manager_thread = None
        self._call_queue = None  # type: ignore
        if self._result_queue is not None and wait:
            for _pipe_attr in "_reader", "_writer":
                if (_pipe := getattr(self._result_queue, _pipe_attr, None)) is not None:
                    _pipe.close()
        self._result_queue = None  # type: ignore
        self._processes = None  # type: ignore
        self._executor_manager_thread_wakeup = None  # type: ignore


def _process_worker(
    call_queue: Queue,
    result_queue: SimpleQueue,
    initializer: Callable[..., Any],
    initargs: tuple[Any, ...],
    max_tasks: int | None = None,
) -> None:
    """Evaluates calls from call_queue and places the results in result_queue.

    This worker is run in a separate process.

    Args:
        call_queue: A ctx.Queue of _CallItems that will be read and
            evaluated by the worker.
        result_queue: A ctx.Queue of _ResultItems that will written
            to by the worker.
        initializer: A callable initializer, or None
        initargs: A tuple of args for the initializer
    """
    if initializer is not None:
        try:
            initializer(*initargs)
        except BaseException:  # noqa: BLE001
            _base.LOGGER.critical("Exception in initializer:", exc_info=True)
            return
    num_tasks = 0
    exit_pid = None
    while True:
        call_item = call_queue.get(block=True)
        if call_item is None:
            result_queue.put(os.getpid())
            return

        if max_tasks is not None:
            num_tasks += 1
            if num_tasks >= max_tasks:
                exit_pid = os.getpid()

        try:
            r = call_item.fn(*call_item.args, **call_item.kwargs)
        except BaseException as e:  # noqa: BLE001
            exc = _ExceptionWithTraceback(e, e.__traceback__)
            _sendback_result(
                result_queue,
                call_item.work_id,
                exception=exc,
                exit_pid=exit_pid,
            )
        else:
            _sendback_result(
                result_queue,
                call_item.work_id,
                result=r,
                exit_pid=exit_pid,
            )
            del r

        del call_item

        if exit_pid is not None:
            return


class _ExecutorManagerThread(threading.Thread):
    """Manages the communication between this process and the worker processes.

    The manager is run in a local thread.

    Args:
        executor: A reference to the ProcessPoolExecutor that owns
            this thread. A weakref will be own by the manager as well as
            references to internal objects used to introspect the state of
            the executor.
    """

    def __init__(self, executor: ProcessPoolExecutor) -> None:
        self.thread_wakeup = executor._executor_manager_thread_wakeup  # noqa: SLF001
        self.shutdown_lock = executor._shutdown_lock  # noqa: SLF001

        def weakref_cb(
            _: Any,
            thread_wakeup: _ThreadWakeup = self.thread_wakeup,
            shutdown_lock: Lock = self.shutdown_lock,
        ) -> None:
            mp_util.debug(
                "Executor collected: triggering callback for QueueManager wakeup",
            )
            with shutdown_lock:
                thread_wakeup.wakeup()

        self.executor_reference: weakref.ReferenceType[
            ProcessPoolExecutor
        ] = weakref.ref(executor, weakref_cb)
        self.processes = executor._processes  # noqa: SLF001
        self.call_queue = executor._call_queue  # noqa: SLF001
        self.result_queue = executor._result_queue  # noqa: SLF001
        self.work_ids_queue = executor._work_ids  # noqa: SLF001
        self.max_tasks_per_child = executor._max_tasks_per_child  # noqa: SLF001
        self.pending_work_items = executor._pending_work_items  # noqa: SLF001

        super().__init__()

    def run(self) -> None:
        while True:
            self.add_call_item_to_queue()

            result_item, is_broken, cause = self.wait_result_broken_or_wakeup()

            if is_broken:
                self.terminate_broken(cause)
                return
            if result_item is not None:
                self.process_result_item(result_item)

                process_exited = result_item.exit_pid is not None
                if process_exited:
                    p = self.processes.pop(result_item.exit_pid)
                    p.join()

                del result_item

                if executor := self.executor_reference():
                    if process_exited:
                        with self.shutdown_lock:
                            executor._adjust_process_count()  # noqa: SLF001
                    else:
                        executor._idle_worker_semaphore.release()  # noqa: SLF001
                    del executor

            if self.is_shutting_down():
                self.flag_executor_shutting_down()
                self.add_call_item_to_queue()
                if not self.pending_work_items:
                    self.join_executor_internals()
                    return

    def add_call_item_to_queue(self) -> None:
        while True:
            if self.call_queue.full():
                return
            try:
                work_id = self.work_ids_queue.get(block=False)
            except queue.Empty:
                return
            else:
                work_item = self.pending_work_items[work_id]

                if work_item.future.set_running_or_notify_cancel():
                    self.call_queue.put(
                        _CallItem(
                            work_id,
                            work_item.fn,
                            work_item.args,
                            work_item.kwargs,
                        ),
                        block=True,
                    )
                else:
                    del self.pending_work_items[work_id]
                    continue

    def wait_result_broken_or_wakeup(self) -> tuple[Any, bool, list[str] | None]:
        result_reader = self.result_queue._reader  # noqa: SLF001 # type: ignore
        assert not self.thread_wakeup._closed  # noqa: SLF001,S101
        wakeup_reader = self.thread_wakeup._reader  # noqa: SLF001
        readers = [result_reader, wakeup_reader]
        worker_sentinels = [p.sentinel for p in list(self.processes.values())]
        ready = mp_wait(readers + worker_sentinels)

        cause = None
        is_broken = True
        result_item = None
        if result_reader in ready:
            try:
                result_item = result_reader.recv()
                is_broken = False
            except BaseException as e:  # noqa: BLE001
                cause = format_exception(type(e), e, e.__traceback__)

        elif wakeup_reader in ready:
            is_broken = False

        with self.shutdown_lock:
            self.thread_wakeup.clear()

        return result_item, is_broken, cause

    def process_result_item(self, result_item: _ResultItem) -> None:
        if isinstance(result_item, int):
            assert self.is_shutting_down()  # noqa: S101
            p = self.processes.pop(result_item)
            p.join()
            if not self.processes:
                self.join_executor_internals()
                return
        else:
            work_item = self.pending_work_items.pop(result_item.work_id, None)
            if work_item is not None:
                if result_item.exception:
                    work_item.future.set_exception(result_item.exception)
                else:
                    work_item.future.set_result(result_item.result)

    def is_shutting_down(self) -> bool:
        executor = self.executor_reference()
        return (
            _global_shutdown
            or executor is None
            or executor._shutdown_thread  # noqa: SLF001
        )

    def terminate_broken(self, cause: list[str] | None) -> None:
        executor = self.executor_reference()
        if executor is not None:
            executor._broken = (  # noqa: SLF001
                "A child process terminated "
                "abruptly, the process pool is not "
                "usable anymore"
            )
            executor._shutdown_thread = True  # noqa: SLF001
            executor = None

        bpe = BrokenProcessPool(
            "A process in the process pool was "
            "terminated abruptly while the future was "
            "running or pending.",
        )
        if cause is not None:
            bpe.__cause__ = _RemoteTraceback(f"\n'''\n{''.join(cause)}'''")

        for work_id, work_item in self.pending_work_items.items():  # noqa: B007
            work_item.future.set_exception(bpe)
            del work_item
        self.pending_work_items.clear()

        for p in self.processes.values():
            p.terminate()

        self.join_executor_internals()

    def flag_executor_shutting_down(self) -> None:
        executor = self.executor_reference()
        if executor is not None:
            executor._shutdown_thread = True  # noqa: SLF001
            if executor._cancel_pending_futures:  # noqa: SLF001
                new_pending_work_items = {}
                for work_id, work_item in self.pending_work_items.items():
                    if not work_item.future.cancel():
                        new_pending_work_items[work_id] = work_item
                self.pending_work_items = new_pending_work_items
                while True:
                    try:
                        self.work_ids_queue.get_nowait()
                    except queue.Empty:
                        break
                executor._cancel_pending_futures = False  # noqa: SLF001

    def shutdown_workers(self) -> None:
        n_children_to_stop = self.get_n_children_alive()
        n_sentinels_sent = 0
        while n_sentinels_sent < n_children_to_stop and self.get_n_children_alive() > 0:
            for i in range(n_children_to_stop - n_sentinels_sent):  # noqa: B007
                try:
                    self.call_queue.put_nowait(None)
                    n_sentinels_sent += 1
                except queue.Full:
                    break

    def join_executor_internals(self) -> None:
        self.shutdown_workers()
        self.call_queue.close()
        self.call_queue.join_thread()
        with self.shutdown_lock:
            self.thread_wakeup.close()
        for p in self.processes.values():
            p.join()

    def get_n_children_alive(self) -> int:
        return sum(p.is_alive() for p in self.processes.values())


def _sendback_result(
    result_queue: SimpleQueue,
    work_id: int,
    result: Any | None = None,
    exception: Exception | _ExceptionWithTraceback | None = None,
    exit_pid: int | None = None,
) -> None:
    """Safely send back the given result or exception"""
    try:
        result_queue.put(
            _ResultItem(work_id, result=result, exception=exception, exit_pid=exit_pid),
        )
    except BaseException as e:  # noqa: BLE001
        exc = _ExceptionWithTraceback(e, e.__traceback__)
        result_queue.put(
            _ResultItem(work_id, exception=exc, exit_pid=exit_pid),
        )


def _rebuild_exc(exc: BaseException, tb: str) -> BaseException:
    exc.__cause__ = _RemoteTraceback(tb)
    return exc


_threads_wakeups = weakref.WeakKeyDictionary()
