"""Helm-specific errors (FR12's helpers)."""

from __future__ import annotations

from typing import Any

ERROR_HELM_RELEASE_NOT_FOUND = "helm_release_not_found"
ERROR_HELM_RELEASE_DECODE_FAILED = "helm_release_decode_failed"


def _base(context: str, code: str) -> dict[str, Any]:
    return {"context": context, "error": code}


def helm_release_not_found(
    context: str,
    release: str,
    namespace: str,
) -> dict[str, Any]:
    """k_get_helm_release: no Secret with Helm labels matching the release name exists."""
    out = _base(context, ERROR_HELM_RELEASE_NOT_FOUND)
    out["release"] = release
    out["namespace"] = namespace
    return out


def helm_release_decode_failed(
    context: str,
    release: str,
    namespace: str,
    *,
    stage: str,
    detail: str,
) -> dict[str, Any]:
    """k_get_helm_release: the .data.release value failed to decode at a specific stage.

    stage is one of {"base64", "gzip", "json"} — names exactly which decode step broke.
    """
    out = _base(context, ERROR_HELM_RELEASE_DECODE_FAILED)
    out["release"] = release
    out["namespace"] = namespace
    out["stage"] = stage
    out["detail"] = detail
    return out
