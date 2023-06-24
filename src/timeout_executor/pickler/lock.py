from __future__ import annotations

from threading import RLock

__all__ = ["patch_lock"]

patch_lock = RLock()
