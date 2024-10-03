# timeout-executor

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![github action](https://github.com/phi-friday/timeout-executor/actions/workflows/check.yaml/badge.svg?event=push&branch=dev)](#)
[![codecov](https://codecov.io/gh/phi-friday/timeout-executor/graph/badge.svg?token=CTXXAD3C0U)](https://codecov.io/gh/phi-friday/timeout-executor)
[![PyPI version](https://badge.fury.io/py/timeout-executor.svg)](https://badge.fury.io/py/timeout-executor)
[![python version](https://img.shields.io/pypi/pyversions/timeout_executor.svg)](#)

## how to install
```shell
$ pip install timeout_executor
# or
$ pip install "timeout_executor[uvloop]"
# or
$ pip install "timeout_executor[jinja]"
```

## how to use
```python
from __future__ import annotations

import time

import anyio

from timeout_executor import AsyncResult, TimeoutExecutor


def sample_sync_func(x: float) -> str:
    time.sleep(x)
    return "done"


async def sample_async_func(x: float) -> str:
    await anyio.sleep(x)
    return "done"


def main() -> None:
    executor = TimeoutExecutor(2)
    result = executor.apply(sample_sync_func, 10)
    assert isinstance(result, AsyncResult)

    try:
        value = result.result()
    except Exception as exc:
        assert isinstance(exc, TimeoutError)

    result = executor.apply(sample_async_func, 1)
    assert isinstance(result, AsyncResult)
    value = result.result()
    assert value == "done"

    result = executor.apply(lambda: "done")
    assert isinstance(result, AsyncResult)
    value = result.result()
    assert value == "done"


async def async_main() -> None:
    executor = TimeoutExecutor(2)
    result = await executor.delay(sample_sync_func, 10)
    assert isinstance(result, AsyncResult)

    try:
        value = await result.delay()
    except Exception as exc:
        assert isinstance(exc, TimeoutError)

    result = await executor.delay(sample_async_func, 1)
    assert isinstance(result, AsyncResult)
    value = await result.delay()
    assert value == "done"

    result = await executor.delay(lambda: "done")
    assert isinstance(result, AsyncResult)
    value = await result.delay()
    assert value == "done"


if __name__ == "__main__":
    main()
    anyio.run(async_main)
```

## License

MIT, see [LICENSE](https://github.com/phi-friday/timeout-executor/blob/main/LICENSE).