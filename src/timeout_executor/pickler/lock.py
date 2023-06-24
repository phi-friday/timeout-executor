from __future__ import annotations

from threading import Lock

__all__ = ["patch_lock"]

patch_lock = Lock()
