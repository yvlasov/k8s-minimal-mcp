"""k_get_secret_to_file tool (PRD §15 FR9).

Write a Secret's decoded content to a local file, never into model context.

A deliberate, named exception to R1 ("tools map to verbs, not resource
types"): Secret is the one resource type whose content must not reach the
model at all, so a resource-specific tool is the right shape here.

Required: context, name, namespace, dst_secret_file
Optional: overwrite (default False)

The response contains only key names and the destination path — never values.
Values that are not valid UTF-8 (or not valid base64 at all) are written to
the file base64-encoded-as-is and listed in the file's `base64_keys` —
lossless passthrough with a per-key flag (FR9 design decision).
"""

from __future__ import annotations

import base64
import binascii
import json
import os
from typing import Any

from ..resolution import resolve, validate, DiscoveryCache
from ..kubectl.runner import run_kubectl_checked
from ..output import envelope
from ..errors import unsafe_path, file_exists, file_write_failed, kubectl_failure


def _decode_secret_data(data: dict[str, str]) -> tuple[dict[str, str], list[str]]:
    """Base64-decode each .data value; undecodable values pass through as-is, flagged."""
    decoded: dict[str, str] = {}
    base64_keys: list[str] = []
    for key, raw_value in data.items():
        try:
            decoded[key] = base64.b64decode(raw_value, validate=True).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError):
            decoded[key] = raw_value
            base64_keys.append(key)
    return decoded, base64_keys


def _write_secret_file(
    dst_secret_file: str,
    decoded: dict[str, str],
    base64_keys: list[str],
) -> str | None:
    """Write the decoded map with 0o600 from creation. Returns an error detail, or None."""
    payload = json.dumps({"data": decoded, "base64_keys": base64_keys}, indent=2)
    try:
        fd = os.open(dst_secret_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload)
        # Overwriting an existing file keeps its old mode — re-assert 0o600.
        os.chmod(dst_secret_file, 0o600)
        return None
    except OSError as e:
        return str(e)


def handle_get_secret_to_file(
    context: str,
    name: str,
    namespace: str,
    dst_secret_file: str,
    *,
    overwrite: bool = False,
    discovery_cache: DiscoveryCache | None = None,
) -> dict[str, Any]:
    """Handle a k_get_secret_to_file call."""
    # Fail-fast: a relative path's target depends on the server's CWD, which
    # the caller has no visibility into — never meaningfully safe.
    if not os.path.isabs(dst_secret_file):
        return envelope(
            unsafe_path(context, dst_secret_file, detail="dst_secret_file must be an absolute path"),
            context, "k_get_secret_to_file", success=False,
        )

    # Fail-fast: refuse to clobber an existing file unless explicitly asked.
    if os.path.exists(dst_secret_file) and not overwrite:
        return envelope(
            file_exists(context, dst_secret_file),
            context, "k_get_secret_to_file", success=False,
        )

    # R8: Secrets are always namespaced — standard resolve/validate.
    res = resolve(context, "secrets", discovery_cache=discovery_cache)
    if isinstance(res, dict) and "error" in res:
        return envelope(res, context, "k_get_secret_to_file", success=False)

    validation = validate(res, "get", namespace)
    if validation:
        validation["context"] = context
        return envelope(validation, context, "k_get_secret_to_file", success=False)

    # One Secret, one way: plain -o json fetch.
    result = run_kubectl_checked(context, ["get", "secret", name, "-n", namespace], output_format="json")
    if "error" in result:
        return envelope(result, context, "k_get_secret_to_file", success=False)

    try:
        secret = json.loads(result["stdout"])
    except json.JSONDecodeError:
        stderr = result.get("stderr", "")
        return envelope(
            kubectl_failure(context, result.get("command", []), f"{stderr} (unparseable JSON output)".strip()),
            context, "k_get_secret_to_file", success=False,
        )

    decoded, base64_keys = _decode_secret_data(secret.get("data") or {})

    write_error = _write_secret_file(dst_secret_file, decoded, base64_keys)
    if write_error is not None:
        return envelope(
            file_write_failed(context, dst_secret_file, detail=write_error),
            context, "k_get_secret_to_file", success=False,
        )

    return envelope(
        {"written_to": dst_secret_file, "keys": list(decoded.keys())},
        context, "k_get_secret_to_file", success=True,
    )
