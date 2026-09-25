"""Access-level → allowed verb set mapping (PRD R7).

Levels:
  readonly   → get, logs, describe
  readwrite  → + apply, patch, delete
  admin      → + exec, get_secret_to_file

Tools are filtered at **registration time** in server.py — the model never
sees tools outside its level. This is not a per-call check.
"""

from __future__ import annotations

from enum import Enum
from typing import FrozenSet


class AccessLevel(str, Enum):
    READONLY = "readonly"
    READWRITE = "readwrite"
    ADMIN = "admin"


_VERB_MAP: dict[AccessLevel, FrozenSet[str]] = {
    AccessLevel.READONLY: frozenset({"get", "logs", "describe", "list_resources", "get_helm_release", "auth_can_i"}),
    AccessLevel.READWRITE: frozenset({"get", "logs", "describe", "list_resources", "get_helm_release", "auth_can_i", "apply", "patch", "delete"}),
    AccessLevel.ADMIN: frozenset({"get", "logs", "describe", "list_resources", "get_helm_release", "auth_can_i", "apply", "patch", "delete", "exec", "get_secret_to_file"}),
}


def allowed_verbs(level: AccessLevel) -> FrozenSet[str]:
    return _VERB_MAP[level]


def tool_for_verb(verb: str) -> str:
    """Return the MCP tool name for a given verb."""
    return f"k_{verb}"
