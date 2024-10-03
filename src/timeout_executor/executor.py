from __future__ import annotations

import os
import shlex
import subprocess
import sys
import tempfile
import textwrap
from collections import deque
from contextlib import suppress
from functools import partial
from itertools import chain
from pathlib import Path
from types import FunctionType
from typing import TYPE_CHECKING, Any, Callable, Generic, overload
from uuid import UUID, uuid4

import anyio
import cloudpickle
from typing_extensions import ParamSpec, Self, TypeVar, override

from timeout_executor.const import (
    SUBPROCESS_COMMAND,
    TIMEOUT_EXECUTOR_INIT_FILE,
    TIMEOUT_EXECUTOR_INPUT_FILE,
)
from timeout_executor.logging import logger
from timeout_executor.result import AsyncResult
from timeout_executor.terminate import Terminator
from timeout_executor.types import (
    Callback,
    CallbackArgs,
    ExecutorArgs,
    InitializerArgs,
    ProcessCallback,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Iterable

    from timeout_executor.main import TimeoutExecutor

__all__ = ["apply_func", "delay_func"]

P = ParamSpec("P")
T = TypeVar("T", infer_variance=True)
P2 = ParamSpec("P2")
T2 = TypeVar("T2", infer_variance=True)
_RM_DECORATORS: frozenset[str] = frozenset(["staticmethod", "lru_cache", "cache"])


class Executor(Callback[P, T], Generic[P, T]):
    __slots__ = (
        "_timeout",
        "_func",
        "_func_name",
        "_unique_id",
        "_init_callbacks",
        "_callbacks",
        "_initializer",
    )

    def __init__(
        self,
        timeout: float,
        func: Callable[P, T],
        callbacks: Callable[[], Iterable[ProcessCallback[P, T]]] | None = None,
        initializer: InitializerArgs[..., Any] | None = None,
    ) -> None:
        self._timeout = timeout
        self._func = func
        self._func_name = func_name(func)
        self._unique_id = uuid4()
        self._init_callbacks = callbacks
        self._callbacks: deque[ProcessCallback[P, T]] = deque()
        self._initializer = initializer

    @property
    def unique_id(self) -> UUID:
        return self._unique_id

    def _create_temp_files(self) -> tuple[Path, Path, Path]:
        """create temp files for input, output and init"""
        temp_dir = Path(tempfile.gettempdir()) / "timeout_executor"
        temp_dir.mkdir(exist_ok=True)

        unique_dir = temp_dir / str(self.unique_id)
        unique_dir.mkdir(exist_ok=False)

        input_file = unique_dir / "input.b"
        output_file = unique_dir / "output.b"
        init_file = unique_dir / "init.b"

        return input_file, output_file, init_file

    def _command(self, stacklevel: int = 2) -> list[str]:
        """create subprocess command"""
        command = f'{sys.executable} -c "{SUBPROCESS_COMMAND}"'
        logger.debug("%r command: %s", self, command, stacklevel=stacklevel)
        return shlex.split(command)

    async def _command_async(self, stacklevel: int = 2) -> list[str]:
        """create subprocess command"""
        raise NotImplementedError

    def _dump_args(
        self, output_file: Path | anyio.Path, *args: P.args, **kwargs: P.kwargs
    ) -> bytes:
        """dump args and output file path to input file"""
        input_args = (self._func, args, kwargs, str(output_file))
        logger.debug("%r before dump input args", self)
        input_args_as_bytes = cloudpickle.dumps(input_args)
        logger.debug(
            "%r after dump input args :: size: %d", self, len(input_args_as_bytes)
        )
        return input_args_as_bytes

    def _dump_initializer(self) -> bytes | None:
        if self._initializer is None:
            logger.debug("%r initializer is None", self)
            return None
        init_args = (
            self._initializer.function,
            self._initializer.args,
            self._initializer.kwargs,
        )
        logger.debug("%r before dump initializer", self)
        init_args_as_bytes = cloudpickle.dumps(init_args)
        logger.debug(
            "%r after dump initializer :: size: %d", self, len(init_args_as_bytes)
        )
        return init_args_as_bytes

    def _create_process(
        self,
        command: list[str],
        input_file: Path | anyio.Path,
        init_file: Path | anyio.Path | None,
        stacklevel: int = 2,
    ) -> subprocess.Popen[str]:
        """create new process"""
        logger.debug("%r before create new process", self, stacklevel=stacklevel)
        process = subprocess.Popen(  # noqa: S603
            command,
            env=os.environ
            | {
                TIMEOUT_EXECUTOR_INPUT_FILE: str(input_file),
                TIMEOUT_EXECUTOR_INIT_FILE: "" if init_file is None else str(init_file),
            },
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        logger.debug("%r process: %d", self, process.pid, stacklevel=stacklevel)
        return process

    def _create_executor_args(
        self,
        input_file: Path | anyio.Path,
        output_file: Path | anyio.Path,
        init_file: Path | anyio.Path | None,
        terminator: Terminator[P, T],
    ) -> ExecutorArgs[P, T]:
        """create executor args"""
        return ExecutorArgs(
            executor=self,
            func_name=self._func_name,
            terminator=terminator,
            input_file=Path(input_file),
            output_file=Path(output_file),
            init_file=Path(init_file) if init_file is not None else None,
            timeout=self._timeout,
        )

    def _init_process(
        self,
        command: list[str],
        input_file: Path | anyio.Path,
        output_file: Path | anyio.Path,
        init_file: Path | anyio.Path | None,
        stacklevel: int = 2,
    ) -> AsyncResult[P, T]:
        """init process.

        before end process
        ---
        1. create terminator
        2. create process
        3. create result container
        4. setup terminator
        5. watch terminator

        after end process
        ---
        6. end process
        7. return result
        8. run terminator
        """
        logger.debug("%r before init process", self, stacklevel=stacklevel)
        executor_args_builder = partial(
            self._create_executor_args, input_file, output_file, init_file
        )
        terminator = Terminator(executor_args_builder, self.callbacks)
        process = self._create_process(
            command, input_file, init_file, stacklevel=stacklevel + 1
        )
        result: AsyncResult[P, T] = AsyncResult(process, terminator.executor_args)
        terminator.callback_args = CallbackArgs(process=process, result=result)
        terminator.start()
        logger.debug("%r after init process", self, stacklevel=stacklevel)
        return result

    def apply(self, *args: P.args, **kwargs: P.kwargs) -> AsyncResult[P, T]:
        """run function with deadline"""
        input_file, output_file, init_file = self._create_temp_files()
        input_args_as_bytes = self._dump_args(output_file, *args, **kwargs)

        logger.debug("%r before write input file", self)
        with input_file.open("wb+") as file:
            file.write(input_args_as_bytes)
        logger.debug("%r after write input file", self)

        init_args_as_bytes = self._dump_initializer()
        if init_args_as_bytes is None:
            init_file = None
        else:
            logger.debug("%r before write init file", self)
            with init_file.open("wb+") as file:
                file.write(init_args_as_bytes)
            logger.debug("%r after write init file", self)

        command = self._command(stacklevel=2)
        return self._init_process(command, input_file, output_file, init_file)

    async def delay(self, *args: P.args, **kwargs: P.kwargs) -> AsyncResult[P, T]:
        """run function with deadline"""
        input_file, output_file, init_file = self._create_temp_files()
        input_file, output_file, init_file = (
            anyio.Path(input_file),
            anyio.Path(output_file),
            anyio.Path(init_file),
        )
        input_args_as_bytes = self._dump_args(output_file, *args, **kwargs)

        logger.debug("%r before write input file", self)
        async with await input_file.open("wb+") as file:
            await file.write(input_args_as_bytes)
        logger.debug("%r after write input file", self)

        init_args_as_bytes = self._dump_initializer()
        if init_args_as_bytes is None:
            init_file = None
        else:
            logger.debug("%r before write init file", self)
            async with await init_file.open("wb+") as file:
                await file.write(init_args_as_bytes)
            logger.debug("%r after write init file", self)

        try:
            command = await self._command_async(stacklevel=2)
        except NotImplementedError:
            command = self._command(stacklevel=2)

        return self._init_process(command, input_file, output_file, init_file)

    @override
    def __repr__(self) -> str:
        return f"<{type(self).__name__}: {self._func_name}>"

    @override
    def callbacks(self) -> Iterable[ProcessCallback[P, T]]:
        if self._init_callbacks is None:
            return self._callbacks.copy()
        return chain(self._init_callbacks(), self._callbacks.copy())

    @override
    def add_callback(self, callback: ProcessCallback[P, T]) -> Self:
        self._callbacks.append(callback)
        return self

    @override
    def remove_callback(self, callback: ProcessCallback[P, T]) -> Self:
        with suppress(ValueError):
            self._callbacks.remove(callback)
        return self


class JinjaExecutor(Executor[P, T], Generic[P, T]):
    __slots__ = (*Executor.__slots__, "_j2_script")
    _j2_script: Path | None

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._j2_script = None

    def _cleanup(self, *args: Any, **kwargs: Any) -> None:  # noqa: ARG002
        if self._j2_script is None:
            return
        with suppress(FileNotFoundError):
            self._j2_script.unlink()
        self._j2_script = None

    @override
    def _dump_args(
        self, output_file: Path | anyio.Path, *args: P.args, **kwargs: P.kwargs
    ) -> bytes:
        """dump args and output file path to input file"""
        input_args = (None, args, kwargs, str(output_file))
        logger.debug("%r before dump input args", self)
        input_args_as_bytes = cloudpickle.dumps(input_args)
        logger.debug(
            "%r after dump input args :: size: %d", self, len(input_args_as_bytes)
        )
        return input_args_as_bytes

    @override
    def _dump_initializer(self) -> bytes | None:
        if self._initializer is None:
            logger.debug("%r initializer is None", self)
            return None
        init_args = (None, self._initializer.args, self._initializer.kwargs)
        logger.debug("%r before dump initializer", self)
        init_args_as_bytes = cloudpickle.dumps(init_args)
        logger.debug(
            "%r after dump initializer :: size: %d", self, len(init_args_as_bytes)
        )
        return init_args_as_bytes

    @override
    def callbacks(self) -> Iterable[Callable[[CallbackArgs[P, T]], Any]]:
        callbacks = super().callbacks()
        return chain([self._cleanup], callbacks)

    @override
    def _command(self, stacklevel: int = 2) -> list[str]:
        j2_script = self._render_jinja_subprocess()
        self._j2_script = Path(tempfile.gettempdir()) / str(uuid4())
        with self._j2_script.open("w+") as file:
            file.write(j2_script)
        command = f"{sys.executable} {self._j2_script}"
        logger.debug("%r command: %s", self, command, stacklevel=stacklevel)
        return shlex.split(command)

    @override
    async def _command_async(self, stacklevel: int = 2) -> list[str]:
        j2_script = await self._render_async_jinja_subprocess()
        self._j2_script = Path(tempfile.gettempdir()) / str(uuid4())
        async with await anyio.Path(self._j2_script).open("w+") as file:
            await file.write(j2_script)
        command = f"{sys.executable} {self._j2_script}"
        logger.debug("%r command: %s", self, command, stacklevel=stacklevel)
        return shlex.split(command)

    def _prepare_func_code(self) -> tuple[str, str, str, str]:
        if self._initializer is None:
            init_func_code = "    def empty_initializer(): pass"
            init_func_name = "empty_initializer"
        else:
            init_func_code, init_func_name = parse_func_code(self._initializer.function)
        func_code, func_name = parse_func_code(self._func)
        func_code = textwrap.indent(func_code, "    ")

        return init_func_code, init_func_name, func_code, func_name

    def _render_jinja_subprocess(self) -> str:
        import jinja2

        init_func_code, init_func_name, func_code, func_name = self._prepare_func_code()
        with Path(__file__).with_name("subprocess_jinja.py").open("r") as file:
            source = file.read()
        return jinja2.Template(source).render(
            func_code=func_code,
            func_name=func_name,
            init_func_code=init_func_code,
            init_func_name=init_func_name,
        )

    async def _render_async_jinja_subprocess(self) -> str:
        import jinja2

        init_func_code, init_func_name, func_code, func_name = self._prepare_func_code()
        async with (
            await anyio.Path(__file__)
            .with_name("subprocess_jinja.py")
            .open("r") as file
        ):
            source = await file.read()
        return await jinja2.Template(source, enable_async=True).render_async(
            func_code=func_code,
            func_name=func_name,
            init_func_code=init_func_code,
            init_func_name=init_func_name,
        )


@overload
def apply_func(
    timeout_or_executor: float | TimeoutExecutor,
    func: Callable[P2, Awaitable[T2]],
    *args: P2.args,
    **kwargs: P2.kwargs,
) -> AsyncResult[P2, T2]: ...


@overload
def apply_func(
    timeout_or_executor: float | TimeoutExecutor,
    func: Callable[P2, T2],
    *args: P2.args,
    **kwargs: P2.kwargs,
) -> AsyncResult[P2, T2]: ...


def apply_func(
    timeout_or_executor: float | TimeoutExecutor,
    func: Callable[P2, Any],
    *args: P2.args,
    **kwargs: P2.kwargs,
) -> AsyncResult[P2, Any]:
    """run function with deadline

    Args:
        timeout_or_executor: deadline
        func: func(sync or async)
        *args: func args
        **kwargs: func kwargs

    Returns:
        async result container
    """
    executor_type = (
        JinjaExecutor
        if not isinstance(timeout_or_executor, (int, float))
        and timeout_or_executor.use_jinja
        else Executor
    )

    if isinstance(timeout_or_executor, (float, int)):
        executor = executor_type(timeout_or_executor, func)
    else:
        executor = executor_type(
            timeout_or_executor.timeout,
            func,
            timeout_or_executor.callbacks,
            timeout_or_executor.initializer,
        )
    return executor.apply(*args, **kwargs)


@overload
async def delay_func(
    timeout_or_executor: float | TimeoutExecutor,
    func: Callable[P2, Awaitable[T2]],
    *args: P2.args,
    **kwargs: P2.kwargs,
) -> AsyncResult[P2, T2]: ...


@overload
async def delay_func(
    timeout_or_executor: float | TimeoutExecutor,
    func: Callable[P2, T2],
    *args: P2.args,
    **kwargs: P2.kwargs,
) -> AsyncResult[P2, T2]: ...


async def delay_func(
    timeout_or_executor: float | TimeoutExecutor,
    func: Callable[P2, Any],
    *args: P2.args,
    **kwargs: P2.kwargs,
) -> AsyncResult[P2, Any]:
    """run function with deadline

    Args:
        timeout_or_executor: deadline
        func: func(sync or async)
        *args: func args
        **kwargs: func kwargs

    Returns:
        async result container
    """
    executor_type = (
        JinjaExecutor
        if not isinstance(timeout_or_executor, (int, float))
        and timeout_or_executor.use_jinja
        else Executor
    )

    if isinstance(timeout_or_executor, (float, int)):
        executor = executor_type(timeout_or_executor, func)
    else:
        executor = executor_type(
            timeout_or_executor.timeout, func, timeout_or_executor.callbacks
        )
    return await executor.delay(*args, **kwargs)


def func_name(func: Callable[..., Any]) -> str:
    if isinstance(func, FunctionType) or is_class(func):
        return func.__module__ + "." + func.__qualname__
    _class = type(func)
    return _class.__module__ + "." + _class.__qualname__


def is_class(obj: Any) -> bool:
    if isinstance(obj, type):
        return True

    meta = type(obj)
    return issubclass(meta, type)


def parse_func_code(func: Callable[..., Any]) -> tuple[str, str]:
    if func.__name__ == "<lambda>":
        raise ValueError("lambda function is not supported")

    import inspect

    source = inspect.getsource(func)
    source = textwrap.dedent(source)
    source = remove_decorators(source)

    return source, func.__name__


def remove_decorators(source: str) -> str:
    import ast

    module = ast.parse(source)

    for node in module.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        decorators = [
            decorator
            for decorator in node.decorator_list
            if (
                not isinstance(decorator, ast.Name)
                or decorator.id not in _RM_DECORATORS
            )
        ]
        if len(decorators) == node.decorator_list:
            continue

        node.decorator_list = decorators

    return ast.unparse(module)
