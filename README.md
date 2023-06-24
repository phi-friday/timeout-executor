# timeout-executor

## how to install
```shell
$ pip install timeout_executor
# or
$ pip install "timeout_executor[all]"
# or
$ pip install "timeout_executor[billiard]"
# or
$ pip install "timeout_executor[dill]"
# or
$ pip install "timeout_executor[cloudpickle]"
```

## how to use
```python
import time

from timeout_executor import TimeoutExecutor


def sample_func() -> None:
    time.sleep(10)


executor = TimeoutExecutor(1)
try:
    executor.apply(sample_func)
except Exception as exc:
    assert isinstance(exc, TimeoutError)

executor = TimeoutExecutor(1, pickler="dill")  # or cloudpickle
result = executor.apply(lambda: "done")
assert result == "done"
```

## License

MIT, see [LICENSE](https://github.com/phi-friday/timeout-executor/blob/main/LICENSE).