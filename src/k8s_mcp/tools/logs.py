"""k_logs tool (PRD §6).

GET logs from a pod.

Required: context, pod
Optional: namespace, container, tail, previous, since, since_time, limit_bytes

Default: tail=100, limit_bytes=8192. Response states the bounds applied and
whether truncation (by line count or by byte limit) occurred.
"""

from __future__ import annotations

from typing import Any

from ..kubectl.runner import run_kubectl_checked
from ..output import bound_logs, envelope
from ..resolution import DiscoveryCache, resolve, validate
from ..resolution.grep_filter import compile_grep_pattern, filter_lines

DEFAULT_LOG_LIMIT_BYTES = 8192
DEFAULT_LOG_TAIL = 100


def handle_logs(
    context: str,
    pod: str,
    *,
    namespace: str | None = None,
    container: str | None = None,
    tail: int | None = None,
    previous: bool = False,
    since: str | None = None,
    since_time: str | None = None,
    limit_bytes: int | None = None,
    grep: str | None = None,
    grep_ignore_case: bool = False,
    discovery_cache: DiscoveryCache | None = None,
) -> dict[str, Any]:
    """Handle a k_logs call."""
    # Fail-fast: compile grep pattern before resolve()
    grep_compiled = None
    if grep:
        grep_result = compile_grep_pattern(grep, ignore_case=grep_ignore_case)
        if isinstance(grep_result, dict):
            from ..errors import invalid_grep_pattern
            return envelope(
                invalid_grep_pattern(context, grep, detail=grep_result["error"]),
                context, "k_logs", success=False,
            )
        grep_compiled = grep_result

    # Pods are always in the core table
    res = resolve(context, "pods", discovery_cache=discovery_cache)
    if isinstance(res, dict):
        return envelope(res, context, "k_logs", success=False)

    resource_meta = res

    # Pre-execution validation (R8)
    validation = validate(resource_meta, "logs", namespace)
    if validation:
        validation["context"] = context
        return envelope(validation, context, "k_logs", success=False)

    # Apply defaults (PRD §6, R4)
    effective_tail = tail if tail is not None else DEFAULT_LOG_TAIL
    effective_limit_bytes = limit_bytes if limit_bytes is not None else DEFAULT_LOG_LIMIT_BYTES

    # Build kubectl args
    args = ["logs", pod]
    if namespace:
        args.extend(["-n", namespace])
    if container:
        args.extend(["-c", container])
    if previous:
        args.append("--previous")
    if since:
        args.extend(["--since", since])
    if since_time:
        args.extend(["--since-time", since_time])
    args.extend(["--tail", str(effective_tail)])
    args.extend(["--limit-bytes", str(effective_limit_bytes)])

    # Execute — logs outputs a raw text stream, not JSON (output_format=None omits -o flag;
    # `kubectl logs` doesn't accept -o at all, unlike get/apply/patch)
    result = run_kubectl_checked(context, args, output_format=None)
    if "error" in result:
        return envelope(result, context, "k_logs", success=False)

    # Apply bounding (R10 + R4)
    bounded = bound_logs(result["stdout"], tail=effective_tail, limit_bytes=effective_limit_bytes)

    # Apply grep filter to the text field only, before _bound/_filtered metadata assembly
    if grep_compiled is not None:
        filtered_text, matched, total = filter_lines(bounded["logs"], grep_compiled)  # type: ignore[arg-type]
        bounded["logs"] = filtered_text
        bounded["_filtered"] = {"matched": matched, "total": total}

    return envelope(bounded, context, "k_logs", success=True)
