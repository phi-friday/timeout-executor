from __future__ import annotations

import sys
from pathlib import Path

if sys.version_info < (3, 11):
    import tomli as tomllib  # type: ignore
else:
    import tomllib  # type: ignore

__all__ = ["__version__"]

pyproject_path = Path(__file__).parent.parent.parent / "pyproject.toml"
with pyproject_path.open("rb") as f:
    pyproject = tomllib.load(f)
__version__ = pyproject["tool"]["poetry"]["version"]
