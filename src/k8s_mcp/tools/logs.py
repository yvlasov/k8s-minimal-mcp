"""k_logs tool (PRD §6).

GET logs from a pod.

Required: context, pod
Optional: namespace, container, tail, previous, since, since_time, limit_bytes

Default: tail=100, limit_bytes=8192. Response states the bounds applied and
whether truncation (by line count or by byte limit) occurred.
"""

from __future__ import annotations

from typing import Any

from ..resolution import resolve, validate, DiscoveryCache
from ..kubectl.runner import run_kubectl_checked
from ..output import bound_logs, envelope

DEFAULT_LOG_LIMIT_BYTES = 8192


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
    discovery_cache: DiscoveryCache | None = None,
) -> dict[str, Any]:
    """Handle a k_logs call."""
    # Pods are always in the core table
    res = resolve(context, "pods", discovery_cache=discovery_cache)
    if isinstance(res, dict) and "error" in res:
        return envelope(res, context, "k_logs", success=False)

    resource_meta = res

    # Pre-execution validation (R8)
    validation = validate(resource_meta, "logs", namespace)
    if validation:
        validation["context"] = context
        return envelope(validation, context, "k_logs", success=False)

    # Apply defaults (PRD §6, R4)
    effective_tail = tail if tail is not None else 100
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

    return envelope(bounded, context, "k_logs", success=True)
