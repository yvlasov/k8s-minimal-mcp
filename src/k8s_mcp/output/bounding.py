"""R10: Output bounding for read operations.

Default bounds (reported per R4):
  - k_get: output=name (names only), not full JSON
  - k_logs: tail=100

Every response that applies a bound includes metadata about what was applied
so the model can decide whether to re-request unbounded.
"""

from __future__ import annotations

import json
from typing import Any


def bound_get_names(data: Any) -> dict[str, Any]:
    """Transform k_get JSON into name-only output (default for k_get).

    Returns a dict with:
      - items: list of {name, namespace, kind} dicts
      - _bound: {"output": "name", "truncated": True}
    """
    items: list[dict[str, Any]] = []

    if isinstance(data, dict):
        if not data:
            return {"items": [], "_bound": {"output": "name", "truncated": True}}
        # Could be a single resource or a List type
        if "kind" in data and data["kind"].endswith("List"):
            # List type — iterate .items
            for obj in data.get("items", []):
                items.append(_extract_identity(obj))
        elif "items" in data:
            # List shape (possibly with metadata like _filtered)
            for obj in data.get("items", []):
                items.append(_extract_identity(obj))
        else:
            # Single resource
            items.append(_extract_identity(data))
    elif isinstance(data, list):
        for obj in data:
            items.append(_extract_identity(obj))

    return {
        "items": items,
        "_bound": {"output": "name", "truncated": True},
    }


def bound_logs(stdout: str, *, tail: int | None = None, limit_bytes: int | None = None) -> dict[str, Any]:
    """Apply tail and byte-limit bounds to log output.

    `stdout` is kubectl's own output, already subject to whatever `--limit-bytes`
    was passed to the kubectl invocation — `limit_bytes` here is only used to
    detect and report that a byte truncation likely occurred, not to re-truncate.

    Returns a dict with:
      - logs: the (possibly truncated) log string
      - _bound: metadata about the bound(s) applied
    """
    lines = stdout.splitlines()

    if tail is not None and tail > 0 and len(lines) > tail:
        truncated_lines = lines[-tail:]
        logs_out = "\n".join(truncated_lines)
        bound: dict[str, Any] = {
            "tail": tail,
            "total_lines": len(lines),
            "truncated": True,
        }
    else:
        logs_out = stdout
        bound = {
            "tail": tail if tail else len(lines),
            "truncated": False,
        }

    if limit_bytes is not None:
        bound["limit_bytes"] = limit_bytes
        # kubectl's --limit-bytes returns "at least this many bytes" (stops after
        # completing the line that crosses the limit) — a returned size at or
        # above the limit is the only signal available that truncation occurred.
        if len(stdout.encode("utf-8")) >= limit_bytes:
            bound["truncated"] = True
            bound["message"] = (
                f"output truncated to {limit_bytes} bytes by --limit-bytes; "
                "pass a larger limit_bytes to retrieve more"
            )

    return {"logs": logs_out, "_bound": bound}


def _extract_identity(obj: Any) -> dict[str, Any]:
    """Extract name, namespace, kind from a Kubernetes resource dict."""
    if not isinstance(obj, dict):
        return {}

    metadata = obj.get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}

    return {
        "name": metadata.get("name", ""),
        "namespace": metadata.get("namespace"),
        "kind": obj.get("kind", ""),
    }


def apply_output_format(data: Any, output_format: str | None) -> Any:
    """Apply output format transformation if requested.

    Supported formats: json, yaml, wide.
    If None, returns data unchanged (caller handles default bounding).
    """
    if output_format is None:
        return data

    if output_format in ("json",):
        return data  # already JSON

    if output_format == "yaml":
        # Return as YAML string — requires PyYAML; defer if unavailable
        try:
            import yaml
            return {"_yaml": yaml.safe_dump(data, default_flow_style=False)}
        except ImportError:
            return {"_error": "yaml output requires PyYAML; use json instead"}

    return data
