from __future__ import annotations

import logging
from logging.config import dictConfig
from typing import Any

__all__ = ["logger"]

LOGGING_CONFIG: dict[str, Any] = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "timeout-executor.default": {
            "()": "logging.Formatter",
            "fmt": "%(levelname)s - %(asctime)s :: %(message)s",
        }
    },
    "handlers": {
        "timeout-executor.default": {
            "formatter": "timeout-executor.default",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stderr",
        }
    },
    "loggers": {
        "timeout-executor": {
            "handlers": ["timeout-executor.default"],
            "level": "INFO",
            "propagate": False,
        }
    },
}

dictConfig(LOGGING_CONFIG)
logger = logging.getLogger("timeout-executor")
