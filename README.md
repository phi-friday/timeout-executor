# timeout-executor

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![github action](https://github.com/phi-friday/timeout-executor/actions/workflows/check.yaml/badge.svg?event=push&branch=dev)](#)
[![PyPI version](https://badge.fury.io/py/timeout-executor.svg)](https://badge.fury.io/py/timeout-executor)
[![python version](https://img.shields.io/pypi/pyversions/timeout_executor.svg)](#)

## how to install
```shell
$ pip install timeout_executor
# or
$ pip install "timeout_executor[uvloop]"
```

## how to use
```python
from __future__ import annotations

import time

from timeout_executor import AsyncResult, TimeoutExecutor


def sample_func() -> None:
    time.sleep(10)


executor = TimeoutExecutor(1)
try:
    executor.apply(sample_func)
except Exception as exc:
    assert isinstance(exc, TimeoutError)

executor = TimeoutExecutor(1)
result = executor.apply(lambda: "done")
assert isinstance(result, AsyncResult)
value = result.result()
assert value == "done"
```

## License

MIT, see [LICENSE](https://github.com/phi-friday/timeout-executor/blob/main/LICENSE).