from __future__ import annotations

from typing import Any

import pytest


@pytest.fixture(
    params=[
        pytest.param(("asyncio", {"use_uvloop": False}), id="asyncio"),
        pytest.param(("asyncio", {"use_uvloop": True}), id="asyncio-uvloop"),
        pytest.param(
            ("trio", {"restrict_keyboard_interrupt_to_checkpoints": True}), id="trio"
        ),
    ],
    scope="session",
)
def anyio_backend(request: pytest.FixtureRequest) -> tuple[str, dict[str, Any]]:
    return request.param
