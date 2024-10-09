from __future__ import annotations

import sys
from typing import Any

import pytest

anyio_params = [
    pytest.param(("asyncio", {"use_uvloop": False}), id="asyncio"),
    pytest.param(
        ("trio", {"restrict_keyboard_interrupt_to_checkpoints": True}), id="trio"
    ),
]
if sys.version_info < (3, 13):
    # FIXME: uvloop build error
    # see more: https://github.com/MagicStack/uvloop/issues/622
    anyio_params.append(
        pytest.param(("asyncio", {"use_uvloop": True}), id="asyncio-uvloop")
    )


@pytest.fixture(params=anyio_params, scope="session")
def anyio_backend(request: pytest.FixtureRequest) -> tuple[str, dict[str, Any]]:
    return request.param
