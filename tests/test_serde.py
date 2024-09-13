# pyright: reportUnknownParameterType=false
# pyright: reportMissingParameterType=false
# pyright: reportImplicitOverride=false
from __future__ import annotations

from typing import Any

import httpx

from timeout_executor import serde


def test_httpx_reduce_ex():
    def f() -> Any:
        try:
            httpx.get("http:://invalid/")
        except Exception as e:  # noqa: BLE001
            return e
        return None

    error = f()
    assert isinstance(error, httpx.UnsupportedProtocol)

    ser_error = serde.serialize_error(error)
    de_error = serde.deserialize_error(ser_error)

    assert isinstance(de_error, httpx.UnsupportedProtocol)
    assert hasattr(de_error, "request")
