"""Shared error-response contract per PRD §7.

Every error returns a dict with:
  - context: echoed back from input
  - error: one of the codes below
  - (optional) candidates, hint, suggestions, valid_contexts

Error responses are constructed only via the helpers below so the §7 shape
stays identical everywhere. No tool assembles error dicts ad hoc.
"""

from __future__ import annotations

from typing import Any


# ── Error codes ──────────────────────────────────────────────────────────────

ERROR_AMBIGUOUS_RESOURCE = "ambiguous_resource"
ERROR_UNKNOWN_RESOURCE = "unknown_resource"
ERROR_VERB_UNSUPPORTED = "verb_unsupported"
ERROR_NAMESPACE_INVALID = "namespace_invalid"
ERROR_UNKNOWN_CONTEXT = "unknown_context"
ERROR_ACCESS_DENIED = "access_denied"
ERROR_KUBECTL_FAILURE = "kubectl_failure"
ERROR_EXEC_FAILED = "exec_failed"
ERROR_INVALID_MANIFEST = "invalid_manifest"
ERROR_INVALID_OUTPUT = "invalid_output"
ERROR_INVALID_SELECTOR = "invalid_selector"
ERROR_DISCOVERY_FAILURE = "discovery_failure"
ERROR_INVALID_JSONPATH_TEMPLATE = "invalid_jsonpath_template"
ERROR_UNSAFE_PATH = "unsafe_path"
ERROR_FILE_EXISTS = "file_exists"
ERROR_FILE_WRITE_FAILED = "file_write_failed"

ERROR_FILE_READ_FAILED = "file_read_failed"
ERROR_OBJECT_NOT_FOUND = "object_not_found"
ERROR_HELM_RELEASE_NOT_FOUND = "helm_release_not_found"
ERROR_HELM_RELEASE_DECODE_FAILED = "helm_release_decode_failed"


# ── Helpers ──────────────────────────────────────────────────────────────────

def _base(context: str, code: str) -> dict[str, Any]:
    return {"context": context, "error": code}


def ambiguous_resource(
    context: str,
    candidates: list[str],
    *,
    hint: str = 'specify resource as <name>.<group>',
) -> dict[str, Any]:
    """Multiple GVKs match the same shortname/plural/kind."""
    out = _base(context, ERROR_AMBIGUOUS_RESOURCE)
    out["candidates"] = candidates
    out["hint"] = hint
    return out


def unknown_resource(
    context: str,
    resource: str,
    *,
    suggestions: list[str] | None = None,
) -> dict[str, Any]:
    """No GVK matched the requested resource name."""
    out = _base(context, ERROR_UNKNOWN_RESOURCE)
    out["resource"] = resource
    if suggestions:
        out["suggestions"] = suggestions
    return out


def verb_unsupported(
    context: str,
    resource: str,
    verb: str,
) -> dict[str, Any]:
    """Pre-execution validation (R8): this resource doesn't support the verb."""
    out = _base(context, ERROR_VERB_UNSUPPORTED)
    out["resource"] = resource
    out["verb"] = verb
    return out


def namespace_invalid(
    context: str,
    resource: str,
    *,
    detail: str | None = None,
) -> dict[str, Any]:
    """Cluster-scoped resource given a namespace, or namespaced without one."""
    out = _base(context, ERROR_NAMESPACE_INVALID)
    out["resource"] = resource
    if detail:
        out["detail"] = detail
    return out


def unknown_context(
    context: str,
    valid_contexts: list[str],
) -> dict[str, Any]:
    """Requested context not found in kubeconfig."""
    out = _base(context, ERROR_UNKNOWN_CONTEXT)
    out["valid_contexts"] = valid_contexts
    return out


def access_denied(
    context: str,
    verb: str,
    access_level: str,
) -> dict[str, Any]:
    """Tool outside current access level — shouldn't reach execution, but defensive."""
    out = _base(context, ERROR_ACCESS_DENIED)
    out["verb"] = verb
    out["access_level"] = access_level
    return out


def kubectl_failure(
    context: str,
    command: str,
    stderr: str,
    *,
    exit_code: int | None = None,
) -> dict[str, Any]:
    """Raw kubectl failure — mapped from kubectl/errors.py."""
    out = _base(context, ERROR_KUBECTL_FAILURE)
    out["command"] = command
    out["stderr"] = stderr
    if exit_code is not None:
        out["exit_code"] = exit_code
    return out


def exec_failed(
    context: str,
    pod: str,
    namespace: str | None,
    command: list[str],
    *,
    stderr: str | None = None,
    exit_code: int | None = None,
) -> dict[str, Any]:
    """k_exec: command exited non-zero inside the container."""
    out = _base(context, ERROR_EXEC_FAILED)
    out["pod"] = pod
    if namespace:
        out["namespace"] = namespace
    out["command"] = command
    if stderr:
        out["stderr"] = stderr
    if exit_code is not None:
        out["exit_code"] = exit_code
    return out


def invalid_manifest(
    context: str,
    *,
    detail: str | None = None,
) -> dict[str, Any]:
    """k_apply: manifest failed to parse or is missing required fields."""
    out = _base(context, ERROR_INVALID_MANIFEST)
    if detail:
        out["detail"] = detail
    return out


def invalid_output(
    context: str,
    output: str,
    *,
    detail: str | None = None,
) -> dict[str, Any]:
    """k_get/k_apply/k_patch: output=jsonpath requested without jsonpath_template."""
    out = _base(context, ERROR_INVALID_OUTPUT)
    out["output"] = output
    if detail:
        out["detail"] = detail
    return out


def invalid_selector(
    context: str,
    selector: str,
    *,
    detail: str | None = None,
) -> dict[str, Any]:
    """k_get: annotation_selector has invalid syntax."""
    out = _base(context, ERROR_INVALID_SELECTOR)
    out["selector"] = selector
    if detail:
        out["detail"] = detail
    return out


def discovery_failure(
    context: str,
    *,
    detail: str,
) -> dict[str, Any]:
    """Discovery cache: kubectl api-resources returned empty/unparseable output."""
    out = _base(context, ERROR_DISCOVERY_FAILURE)
    out["detail"] = detail
    return out


def invalid_jsonpath_template(
    context: str,
    template: str,
    *,
    detail: str | None = None,
) -> dict[str, Any]:
    """k_get/k_apply/k_patch: jsonpath_template contains nested braces (invalid syntax)."""
    out = _base(context, ERROR_INVALID_JSONPATH_TEMPLATE)
    out["jsonpath_template"] = template
    if detail:
        out["detail"] = detail
    return out


def unsafe_path(
    context: str,
    path: str,
    *,
    detail: str | None = None,
) -> dict[str, Any]:
    """k_get_secret_to_file: dst_secret_file failed the path-safety check (e.g. not absolute)."""
    out = _base(context, ERROR_UNSAFE_PATH)
    out["path"] = path
    if detail:
        out["detail"] = detail
    return out


def file_exists(
    context: str,
    path: str,
) -> dict[str, Any]:
    """k_get_secret_to_file: destination file already exists and overwrite is not set."""
    out = _base(context, ERROR_FILE_EXISTS)
    out["path"] = path
    return out


def file_write_failed(
    context: str,
    path: str,
    *,
    detail: str | None = None,
) -> dict[str, Any]:
    """k_get_secret_to_file: writing the decoded Secret to disk failed (permissions, missing parent dir)."""
    out = _base(context, ERROR_FILE_WRITE_FAILED)
    out["path"] = path
    if detail:
        out["detail"] = detail
    return out


def file_read_failed(
    context: str,
    path: str,
    *,
    detail: str | None = None,
) -> dict[str, Any]:
    """k_apply: reading the manifest from src_file failed (missing file, permissions, undecodable content)."""
    out = _base(context, ERROR_FILE_READ_FAILED)
    out["path"] = path
    if detail:
        out["detail"] = detail
    return out


def object_not_found(
    context: str,
    resource: str | None = None,
    *,
    name: str | None = None,
    raw_stderr: str | None = None,
) -> dict[str, Any]:
    """kubectl returned NotFound for a resolved resource type — the named object doesn't exist."""
    out = _base(context, ERROR_OBJECT_NOT_FOUND)
    if resource is not None:
        out["resource"] = resource
    if name:
        out["name"] = name
    if raw_stderr:
        out["raw_stderr"] = raw_stderr
    return out


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
