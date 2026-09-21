"""k_describe tool (PRD §6, pending §13).

Delegates verbatim to `kubectl describe`. Output is verbose unstructured text.

Implemented behind a conditional flag — see server.py for registration logic.
"""

from __future__ import annotations

from typing import Any

from ..resolution import resolve, validate, DiscoveryCache
from ..kubectl.runner import run_kubectl_checked
from ..output import envelope


def handle_describe(
    context: str,
    resource: str,
    name: str,
    *,
    namespace: str | None = None,
    discovery_cache: DiscoveryCache | None = None,
) -> dict[str, Any]:
    """Handle a k_describe call — delegates to kubectl describe verbatim."""
    # Resolve resource → GVK
    res = resolve(context, resource, discovery_cache=discovery_cache)
    if isinstance(res, dict) and "error" in res:
        return envelope(res, context, "k_describe", success=False)

    resource_meta = res

    # Pre-execution validation (R8)
    validation = validate(resource_meta, "get", namespace)
    if validation:
        validation["context"] = context
        return envelope(validation, context, "k_describe", success=False)

    # Build kubectl args
    args = ["describe", resource_meta.canonical, name]
    if namespace:
        args.extend(["-n", namespace])

    # Execute — describe outputs text, not JSON (output_format=None omits -o flag)
    result = run_kubectl_checked(context, args, output_format=None)
    if "error" in result:
        return envelope(result, context, "k_describe", success=False)

    return envelope({
        "output": result["stdout"],
    }, context, "k_describe", success=True)
