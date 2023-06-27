from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from timeout_executor.serde.main import PicklerType


unpatch: frozenset[PicklerType] = frozenset({"pickle", "cloudpickle"})
replace: dict[PicklerType, PicklerType] = {"pickle": "cloudpickle"}
order: tuple[PicklerType, ...] = ("cloudpickle", "dill")
