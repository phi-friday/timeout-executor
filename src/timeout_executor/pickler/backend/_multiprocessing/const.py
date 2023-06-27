from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from timeout_executor.pickler.main import PicklerType


unpatch: frozenset[PicklerType] = frozenset({"pickle"})
replace: dict[PicklerType, PicklerType] = {}
order: tuple[PicklerType, ...] = ("dill", "cloudpickle", "pickle")
