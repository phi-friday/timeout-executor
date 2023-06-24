from __future__ import annotations

import logging

__all__ = ["logger"]

logger = logging.getLogger("timeout_executor")
logger.setLevel(logging.INFO)
