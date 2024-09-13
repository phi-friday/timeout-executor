from __future__ import annotations

__all__ = ["TIMEOUT_EXECUTOR_INPUT_FILE", "SUBPROCESS_COMMAND"]
TIMEOUT_EXECUTOR_INPUT_FILE = "_TIMEOUT_EXECUTOR_INPUT_FILE"
TIMEOUT_EXECUTOR_INIT_FILE = "_TIMEOUT_EXECUTOR_INIT_FILE"
SUBPROCESS_COMMAND = (
    "from timeout_executor.subprocess import run_in_subprocess;run_in_subprocess()"
)
