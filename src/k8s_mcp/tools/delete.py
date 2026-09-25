"""k_delete tool (PRD §6).

Delete a Kubernetes resource.

Required: context, resource
Optional: name, namespace, label_selector, dry_run
"""

from __future__ import annotations

import json
from typing import Any

from ..resolution import resolve, validate, DiscoveryCache
from ..kubectl.runner import run_kubectl_checked
from ..output import prune, envelope


def handle_delete(
    context: str,
    resource: str,
    *,
    name: str | None = None,
    namespace: str | None = None,
    label_selector: str | None = None,
    dry_run: str = "none",
    discovery_cache: DiscoveryCache | None = None,
) -> dict[str, Any]:
    """Handle a k_delete call."""
    # Resolve resource → GVK
    res = resolve(context, resource, discovery_cache=discovery_cache)
    if isinstance(res, dict) and "error" in res:
        return envelope(res, context, "k_delete", success=False)

    resource_meta = res

    # Pre-execution validation (R8)
    validation = validate(resource_meta, "delete", namespace)
    if validation:
        validation["context"] = context
        return envelope(validation, context, "k_delete", success=False)

    # Build kubectl args
    args = ["delete", resource_meta.fully_qualified_name]
    if name:
        args.append(name)
    elif label_selector:
        args.append("-l")
        args.append(label_selector)
    if namespace:
        args.extend(["-n", namespace])
    if dry_run != "none":
        args.extend(["--dry-run", dry_run])

    # Execute — delete outputs a plain-text confirmation, not JSON (output_format=None omits -o flag;
    # `kubectl delete` only supports '-o name', unlike get/apply/patch)
    result = run_kubectl_checked(context, args, output_format=None)
    if "error" in result:
        return envelope(result, context, "k_delete", success=False)

    # Parse and prune response
    try:
        data = json.loads(result["stdout"])
        pruned = prune(data, kind=resource_meta.kind)
    except (json.JSONDecodeError, TypeError):
        pruned = {"message": result["stdout"]}

    return envelope({
        "data": pruned,
        "dry_run": dry_run if dry_run != "none" else False,
    }, context, "k_delete", success=True)
