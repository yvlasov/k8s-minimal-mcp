"""k_get_helm_release tool (PRD §15 FR12).

Decode a Helm release's storage Secret into usable metadata.

Helm v3 stores each release revision as a Secret (labels
``owner=helm``, ``name=<release>``, ``version=<revision>``) whose
``.data.release`` value is ``base64(gzip(JSON))``. This tool fetches the
Secret directly via the kubectl runner (same pattern as FR9's
``k_get_secret_to_file``), bypassing ``prune()``'s generic Secret redaction,
and decodes the three-stage wire format into a bounded summary.

Required: context, release, namespace
Optional: revision (default: highest version label), include_manifest (default False)
"""

from __future__ import annotations

import base64
import binascii
import gzip
import json
from typing import Any

from ..resolution import resolve, validate, DiscoveryCache
from ..kubectl.runner import run_kubectl_checked
from ..output import envelope
from ..errors import (
    helm_release_not_found,
    helm_release_decode_failed,
    kubectl_failure,
)


def _decode_release_data(raw_b64: str) -> tuple[dict[str, Any] | None, str | None, str | None]:
    """Decode base64 → gzip → json. Returns (data, error_stage, error_detail)."""
    try:
        compressed = base64.b64decode(raw_b64, validate=True)
    except (binascii.Error, ValueError) as e:
        return None, "base64", str(e)

    try:
        decompressed = gzip.decompress(compressed)
    except (OSError, EOFError) as e:
        return None, "gzip", str(e)

    try:
        data = json.loads(decompressed)
    except json.JSONDecodeError as e:
        return None, "json", str(e)

    return data, None, None


def _select_secret(
    items: list[dict[str, Any]],
    revision: int | None,
) -> dict[str, Any] | None:
    """Pick the Secret for the requested revision, or the highest version label."""
    if revision is not None:
        for item in items:
            labels = item.get("metadata", {}).get("labels", {})
            if labels.get("version") == str(revision):
                return item
        return None

    best: dict[str, Any] | None = None
    best_rev = -1
    for item in items:
        labels = item.get("metadata", {}).get("labels", {})
        try:
            rev = int(labels.get("version", "0"))
        except ValueError:
            continue
        if rev > best_rev:
            best_rev = rev
            best = item
    return best


def handle_get_helm_release(
    context: str,
    release: str,
    namespace: str,
    *,
    revision: int | None = None,
    include_manifest: bool = False,
    discovery_cache: DiscoveryCache | None = None,
) -> dict[str, Any]:
    """Handle a k_get_helm_release call."""
    # R8: Secrets are always namespaced — standard resolve/validate.
    res = resolve(context, "secrets", discovery_cache=discovery_cache)
    if isinstance(res, dict) and "error" in res:
        return envelope(res, context, "k_get_helm_release", success=False)

    validation = validate(res, "get", namespace)
    if validation:
        validation["context"] = context
        return envelope(validation, context, "k_get_helm_release", success=False)

    # List candidates via Helm's own labels.
    result = run_kubectl_checked(
        context,
        ["get", "secret", "-n", namespace, "-l", f"owner=helm,name={release}", "-o", "json"],
        output_format="json",
    )
    if "error" in result:
        return envelope(result, context, "k_get_helm_release", success=False)

    try:
        listing = json.loads(result["stdout"])
    except json.JSONDecodeError:
        stderr = result.get("stderr", "")
        return envelope(
            kubectl_failure(context, result.get("command", []), f"{stderr} (unparseable JSON output)".strip()),
            context, "k_get_helm_release", success=False,
        )

    items = listing.get("items", [])
    if not items:
        return envelope(
            helm_release_not_found(context, release, namespace),
            context, "k_get_helm_release", success=False,
        )

    selected = _select_secret(items, revision)
    if selected is None:
        return envelope(
            helm_release_not_found(context, release, namespace),
            context, "k_get_helm_release", success=False,
        )

    labels = selected.get("metadata", {}).get("labels", {})
    selected_revision = int(labels.get("version", "0"))

    raw_b64 = (selected.get("data") or {}).get("release")
    if raw_b64 is None:
        return envelope(
            helm_release_decode_failed(
                context, release, namespace,
                stage="base64",
                detail="Secret has no .data.release key",
            ),
            context, "k_get_helm_release", success=False,
        )

    data, error_stage, error_detail = _decode_release_data(raw_b64)
    if data is None:
        return envelope(
            helm_release_decode_failed(
                context, release, namespace,
                stage=error_stage or "unknown",
                detail=error_detail or "unknown decode error",
            ),
            context, "k_get_helm_release", success=False,
        )

    info = data.get("info", {})
    chart_metadata = data.get("chart", {}).get("metadata", {})

    response: dict[str, Any] = {
        "release": info.get("name", release),
        "revision": selected_revision,
        "chart": chart_metadata.get("name", ""),
        "chart_version": chart_metadata.get("version", ""),
        "app_version": chart_metadata.get("appVersion", ""),
        "status": info.get("status", ""),
        "first_deployed": info.get("firstDeployed", ""),
        "last_deployed": info.get("lastDeployed", ""),
        "values": data.get("values", {}),
    }
    if include_manifest:
        response["manifest"] = data.get("manifest", "")

    return envelope(response, context, "k_get_helm_release", success=True)
