"""Load the static core resource table from data/core_resources.toml.

Called once at startup. Returns list[ResourceMeta].
"""

from __future__ import annotations

import importlib.resources
from pathlib import Path
from typing import Any

import tomllib

from .models import ResourceMeta

# Path to the TOML data file relative to this package
_DATA_FILE = "data/core_resources.toml"


def _load_toml(raw: bytes) -> list[ResourceMeta]:
    """Parse TOML bytes into a list of ResourceMeta."""
    data: dict[str, Any] = tomllib.loads(raw.decode("utf-8"))
    resources: list[dict[str, Any]] = data.get("resource", [])
    return [ResourceMeta(**r) for r in resources]


def load_core_table() -> list[ResourceMeta]:
    """Load and return the core resource table."""
    pkg = importlib.resources.files("k8s_mcp")
    toml_path: Path = pkg / _DATA_FILE  # type: ignore[operator]
    with toml_path.open("rb") as f:
        return _load_toml(f.read())
