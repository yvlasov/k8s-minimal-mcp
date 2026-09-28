"""Core resolution and tool errors (R2/R6/R7/R8 contract helpers)."""

from __future__ import annotations

from typing import Any

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
ERROR_INVALID_GREP_PATTERN = "invalid_grep_pattern"
ERROR_OBJECT_NOT_FOUND = "object_not_found"
ERROR_KUBECTL_TIMEOUT = "kubectl_timeout"
ERROR_KUBECTL_NOT_INSTALLED = "kubectl_not_installed"
ERROR_KUBECTL_EXEC_ERROR = "kubectl_exec_error"
ERROR_KUBECTL_UNREACHABLE = "kubectl_unreachable"
ERROR_AUTHENTICATION_FAILED = "authentication_failed"
ERROR_KUBECTL_INVALID_ARGUMENT = "kubectl_invalid_argument"
ERROR_OBJECT_INVALID = "object_invalid"


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
    """k_get/k_apply/k_patch: output=jsonpath requested without jsonpath."""
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
    """k_get/k_apply/k_patch: jsonpath contains nested braces (invalid syntax)."""
    out = _base(context, ERROR_INVALID_JSONPATH_TEMPLATE)
    out["jsonpath"] = template
    if detail:
        out["detail"] = detail
    return out


def invalid_grep_pattern(
    context: str,
    pattern: str,
    *,
    detail: str | None = None,
) -> dict[str, Any]:
    """k_logs/k_describe/k_get: grep pattern has invalid regex syntax."""
    out = _base(context, ERROR_INVALID_GREP_PATTERN)
    out["grep"] = pattern
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


def kubectl_timeout(
    context: str,
    *,
    timeout: float,
    command: list[str],
    detail: str | None = None,
) -> dict[str, Any]:
    """subprocess.TimeoutExpired: kubectl exceeded its timeout."""
    out = _base(context, ERROR_KUBECTL_TIMEOUT)
    out["timeout"] = timeout
    out["command"] = command
    if detail:
        out["detail"] = detail
    return out


def kubectl_not_installed(
    context: str,
    *,
    detail: str | None = None,
) -> dict[str, Any]:
    """FileNotFoundError: kubectl binary not in PATH."""
    out = _base(context, ERROR_KUBECTL_NOT_INSTALLED)
    if detail:
        out["detail"] = detail
    return out


def kubectl_exec_error(
    context: str,
    *,
    detail: str,
) -> dict[str, Any]:
    """OSError: kubectl could not be executed (permission denied, etc.)."""
    out = _base(context, ERROR_KUBECTL_EXEC_ERROR)
    out["detail"] = detail
    return out


def kubectl_unreachable(
    context: str,
    *,
    raw_stderr: str,
) -> dict[str, Any]:
    """kubectl failed fast: cluster/network unreachable (DNS, connection refused)."""
    out = _base(context, ERROR_KUBECTL_UNREACHABLE)
    out["raw_stderr"] = raw_stderr
    return out


def authentication_failed(
    context: str,
    *,
    raw_stderr: str,
) -> dict[str, Any]:
    """kubectl: credentials expired/invalid (401), distinct from RBAC denial (403)."""
    out = _base(context, ERROR_AUTHENTICATION_FAILED)
    out["raw_stderr"] = raw_stderr
    return out


def kubectl_invalid_argument(
    context: str,
    *,
    raw_stderr: str,
) -> dict[str, Any]:
    """kubectl CLI rejected the invocation (unknown flag/command)."""
    out = _base(context, ERROR_KUBECTL_INVALID_ARGUMENT)
    out["raw_stderr"] = raw_stderr
    return out


def object_invalid(
    context: str,
    *,
    raw_stderr: str,
) -> dict[str, Any]:
    """API server rejected the object on apply/patch (schema validation)."""
    out = _base(context, ERROR_OBJECT_INVALID)
    out["raw_stderr"] = raw_stderr
    return out
