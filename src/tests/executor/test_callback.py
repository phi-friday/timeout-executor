from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from itertools import chain
from subprocess import Popen
from typing import Any, Generic

import pytest
from typing_extensions import ParamSpec, TypeVar

from tests.executor.base import BaseExecutorTest
from timeout_executor.result import AsyncResult
from timeout_executor.types import CallbackArgs, ProcessCallback, State

_P = ParamSpec("_P")
_T = TypeVar("_T", infer_variance=True)

TEST_SIZE = 3
pytestmark = pytest.mark.anyio


@dataclass(frozen=False)
class CallbackContainer(Generic[_P, _T]):
    value: CallbackArgs[_P, _T] = field(init=False)
    salt: Any = field(init=False)


def callback_factory(
    func: Callable[_P, Any],  # noqa: ARG001
    salt: Any = None,
) -> tuple[ProcessCallback[_P, Any], CallbackContainer[_P, Any]]:
    container = CallbackContainer()

    def callback(args: CallbackArgs[_P, Any]) -> None:
        container.value = args
        container.salt = salt
        if args.state.value is None:
            args.state.value = (container,)
        else:
            args.state.value = (*args.state.value, container)

    return (callback, container)


class TestExecutorSync(BaseExecutorTest):
    def test_apply_callback_one(self):
        callback, container = callback_factory(self.sample_func)
        result = self.executor(1).add_callback(callback).apply(self.sample_func)
        result.result()
        assert isinstance(container.value, CallbackArgs)
        assert isinstance(container.value.process, Popen)
        assert container.value.process.returncode == 0
        assert isinstance(container.value.state, State)
        assert isinstance(container.value.result, AsyncResult)
        assert container.value.result is result

    def test_apply_result_callback_one(self):
        callback, container = callback_factory(self.sample_func)
        result = self.executor(1).apply(self.sample_func)
        result.add_callback(callback)
        result.result()
        assert isinstance(container.value, CallbackArgs)

    def test_apply_callback_many(self):
        callback_0, container_0 = callback_factory(self.sample_func, salt=0)
        callback_1, container_1 = callback_factory(self.sample_func, salt=1)
        result = (
            self.executor(1)
            .add_callback(callback_0)
            .add_callback(callback_1)
            .apply(self.sample_func)
        )
        result.result()
        assert isinstance(container_0.value, CallbackArgs)
        assert isinstance(container_1.value, CallbackArgs)
        assert container_0.value.state.value == (container_0, container_1)
        assert container_1.value.state.value == (container_0, container_1)
        assert container_0.value.state is container_1.value.state

    def test_apply_remove_callback(self):
        callback_0, container_0 = callback_factory(self.sample_func, salt=0)
        callback_1, container_1 = callback_factory(self.sample_func, salt=1)
        result = (
            self.executor(1)
            .add_callback(callback_0)
            .add_callback(callback_1)
            .remove_callback(callback_0)
            .apply(self.sample_func)
        )
        result.result()
        assert not hasattr(container_0, "value")
        assert isinstance(container_1.value, CallbackArgs)
        assert container_1.value.state.value == (container_1,)

    def test_apply_remove_result_callback(self):
        callback_0, container_0 = callback_factory(self.sample_func, salt=0)
        callback_1, container_1 = callback_factory(self.sample_func, salt=1)
        result = self.executor(1).apply(self.sample_func)
        result.add_callback(callback_0).add_callback(callback_1).remove_callback(
            callback_0
        )
        result.result()
        assert not hasattr(container_0, "value")
        assert isinstance(container_1.value, CallbackArgs)
        assert container_1.value.state.value == (container_1,)


class TestExecutorAsync(BaseExecutorTest):
    async def test_delay_callback_one(self):
        callback, container = callback_factory(self.sample_async_func)
        result = (
            await self.executor(1).add_callback(callback).delay(self.sample_async_func)
        )
        await result.delay()
        assert isinstance(container.value, CallbackArgs)
        assert isinstance(container.value.process, Popen)
        assert container.value.process.returncode == 0
        assert isinstance(container.value.state, State)
        assert isinstance(container.value.result, AsyncResult)
        assert container.value.result is result

    async def test_delay_result_callback_one(self):
        callback, container = callback_factory(self.sample_async_func)
        result = await self.executor(1).delay(self.sample_async_func)
        result.add_callback(callback)
        await result.delay()
        assert isinstance(container.value, CallbackArgs)

    async def test_delay_callback_many(self):
        callback_0, container_0 = callback_factory(self.sample_async_func, salt=0)
        callback_1, container_1 = callback_factory(self.sample_async_func, salt=1)
        result = await (
            self.executor(1)
            .add_callback(callback_0)
            .add_callback(callback_1)
            .delay(self.sample_async_func)
        )
        await result.delay()
        assert isinstance(container_0.value, CallbackArgs)
        assert isinstance(container_1.value, CallbackArgs)
        assert container_0.value.state.value == (container_0, container_1)
        assert container_1.value.state.value == (container_0, container_1)
        assert container_0.value.state is container_1.value.state

    async def test_delay_remove_callback(self):
        callback_0, container_0 = callback_factory(self.sample_async_func, salt=0)
        callback_1, container_1 = callback_factory(self.sample_async_func, salt=1)
        result = await (
            self.executor(1)
            .add_callback(callback_0)
            .add_callback(callback_1)
            .remove_callback(callback_0)
            .delay(self.sample_async_func)
        )
        await result.delay()
        assert not hasattr(container_0, "value")
        assert isinstance(container_1.value, CallbackArgs)
        assert container_1.value.state.value == (container_1,)

    async def test_delay_remove_result_callback(self):
        callback_0, container_0 = callback_factory(self.sample_async_func, salt=0)
        callback_1, container_1 = callback_factory(self.sample_async_func, salt=1)
        result = await self.executor(1).delay(self.sample_func)
        result.add_callback(callback_0).add_callback(callback_1).remove_callback(
            callback_0
        )
        await result.delay()
        assert not hasattr(container_0, "value")
        assert isinstance(container_1.value, CallbackArgs)
        assert container_1.value.state.value == (container_1,)


def test_executor_callbacks():
    callbacks: deque[ProcessCallback[..., Any]] = deque()
    for _ in range(10):
        callback, _ = callback_factory(BaseExecutorTest.sample_func)
        callbacks.append(callback)

    executor = BaseExecutorTest.executor(1)
    for callback in callbacks:
        executor.add_callback(callback)

    executor_callbacks = executor.callbacks()
    assert isinstance(executor_callbacks, deque)
    assert len(executor_callbacks) == len(callbacks)
    for executor_callback, callback in zip(executor_callbacks, callbacks):
        assert executor_callback is callback


def test_result_callbacks():
    callbacks: deque[ProcessCallback[..., Any]] = deque()
    for _ in range(10):
        callback, _ = callback_factory(BaseExecutorTest.sample_func)
        callbacks.append(callback)

    result = BaseExecutorTest.executor(1).apply(BaseExecutorTest.sample_func)
    for callback in callbacks:
        result.add_callback(callback)

    result_callbacks = result.callbacks()
    result_callbacks = list(result_callbacks)
    assert len(result_callbacks) == len(callbacks)
    for result_callback, callback in zip(result_callbacks, callbacks):
        assert result_callback is callback


def test_callbacks_all():
    executor_callbacks: deque[ProcessCallback[..., Any]] = deque()
    result_callbacks: deque[ProcessCallback[..., Any]] = deque()
    for _ in range(10):
        callback, _ = callback_factory(BaseExecutorTest.sample_func)
        executor_callbacks.append(callback)
        callback, _ = callback_factory(BaseExecutorTest.sample_func)
        result_callbacks.append(callback)

    executor = BaseExecutorTest.executor(1)
    for callback in executor_callbacks:
        executor.add_callback(callback)

    result = executor.apply(BaseExecutorTest.sample_func)
    for callback in result_callbacks:
        result.add_callback(callback)

    callbacks = result.callbacks()
    callbacks = list(callbacks)
    assert len(callbacks) == len(executor_callbacks) + len(result_callbacks)
    for registered_callback, callback in zip(
        callbacks, chain(executor_callbacks, result_callbacks)
    ):
        assert registered_callback is callback
