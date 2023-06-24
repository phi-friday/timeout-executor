from __future__ import annotations

import sys
from pathlib import Path

if sys.version_info < (3, 11):
    import tomli as tomllib  # type: ignore
else:
    import tomllib  # type: ignore

__all__ = ["__version__"]

pyproject_path = Path(__file__).parent / "pyproject.toml"
try:
    with pyproject_path.open("rb") as f:
        pyproject = tomllib.load(f)
except FileNotFoundError:
    with pyproject_path.parent.parent.with_name(pyproject_path.name).open("rb") as f:
        pyproject = tomllib.load(f)
__version__: str = pyproject["tool"]["poetry"]["version"]
