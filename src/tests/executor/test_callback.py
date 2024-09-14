from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
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
    func: Callable[_P, _T],  # noqa: ARG001
    salt: Any = None,
) -> tuple[ProcessCallback[_P, _T], CallbackContainer[_P, _T]]:
    container = CallbackContainer()

    def callback(args: CallbackArgs[_P, _T]) -> None:
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
