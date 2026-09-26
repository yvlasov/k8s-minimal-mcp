"""k_exec tool (PRD §6).

Execute a command inside a pod container.

Required: context, pod, command
Optional: namespace, container

Admin-only access level (R7).
"""

from __future__ import annotations

from typing import Any

from ..resolution import resolve, validate, DiscoveryCache
from ..kubectl.runner import run_kubectl_checked
from ..output import envelope
from ..errors import exec_failed


def handle_exec(
    context: str,
    pod: str,
    command: list[str],
    *,
    namespace: str | None = None,
    container: str | None = None,
    discovery_cache: DiscoveryCache | None = None,
) -> dict[str, Any]:
    """Handle a k_exec call."""
    # Pods are always in the core table
    res = resolve(context, "pods", discovery_cache=discovery_cache)
    if isinstance(res, dict) and "error" in res:
        return envelope(res, context, "k_exec", success=False)

    resource_meta = res

    # Pre-execution validation (R8)
    validation = validate(resource_meta, "exec", namespace)
    if validation:
        validation["context"] = context
        return envelope(validation, context, "k_exec", success=False)

    # Build kubectl args
    args = ["exec", pod]
    if namespace:
        args.extend(["-n", namespace])
    if container:
        args.extend(["-c", container])
    args.append("--")
    args.extend(command)

    # Execute — exec needs different handling (no -o json)
    result = run_kubectl_checked(context, args, output_format=None)
    if "error" in result:
        # kubectl_failure from map_kubectl_error — not exec_failed shape
        if result.get("error") == "kubectl_failure":
            return envelope(
                exec_failed(
                    context=context,
                    pod=pod,
                    namespace=namespace,
                    command=command,
                    stderr=result.get("raw_stderr", result.get("stderr", "")),
                    exit_code=result.get("exit_code", 1),
                ),
                context, "k_exec", success=False,
            )
        return envelope(result, context, "k_exec", success=False)

    return envelope({
        "stdout": result["stdout"],
        "stderr": result["stderr"],
        "exit_code": result["returncode"],
    }, context, "k_exec", success=True)
