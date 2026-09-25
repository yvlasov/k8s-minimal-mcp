"""k_patch tool (PRD §6).

Patch a Kubernetes resource.

Required: context, resource, name, patch
Optional: namespace, type (strategic/merge/json), dry_run
"""

from __future__ import annotations

import json
from typing import Any

from ..resolution import resolve, validate, DiscoveryCache
from ..resolution.jsonpath_validation import check_nested_braces
from ..kubectl.runner import run_kubectl_checked
from ..output import prune, envelope, apply_output_format
from ..errors import invalid_output, invalid_jsonpath_template


def handle_patch(
    context: str,
    resource: str,
    name: str,
    patch: str,
    *,
    namespace: str | None = None,
    type: str = "strategic",  # "strategic", "merge", "json"
    dry_run: str = "none",
    output: str | None = None,
    jsonpath_template: str | None = None,
    discovery_cache: DiscoveryCache | None = None,
) -> dict[str, Any]:
    """Handle a k_patch call."""
    # Fail-fast: output=jsonpath without template
    if output == "jsonpath" and not jsonpath_template:
        return envelope(
            invalid_output(context, output),
            context, "k_patch", success=False,
        )

    # Fail-fast: output=wide not supported on patch (kubectl's -o wide has no meaning for apply/patch)
    if output == "wide":
        return envelope(
            invalid_output(context, output),
            context, "k_patch", success=False,
        )

    # Fail-fast: nested-brace jsonpath_template (FR8)
    if jsonpath_template:
        nested_err = check_nested_braces(jsonpath_template)
        if nested_err:
            return envelope(
                invalid_jsonpath_template(context, jsonpath_template, detail=nested_err),
                context, "k_patch", success=False,
            )

    # Resolve resource → GVK
    res = resolve(context, resource, discovery_cache=discovery_cache)
    if isinstance(res, dict) and "error" in res:
        return envelope(res, context, "k_patch", success=False)

    resource_meta = res

    # Pre-execution validation (R8)
    validation = validate(resource_meta, "patch", namespace)
    if validation:
        validation["context"] = context
        return envelope(validation, context, "k_patch", success=False)

    # Build kubectl args
    args = ["patch", resource_meta.fully_qualified_name, name]
    if namespace:
        args.extend(["-n", namespace])
    args.extend(["--type", type])
    if dry_run != "none":
        args.extend(["--dry-run", dry_run])

    # Execute
    if jsonpath_template:
        result = run_kubectl_checked(context, args, stdin=patch, output_format=f"jsonpath={jsonpath_template}")
        if "error" in result:
            return envelope(result, context, "k_patch", success=False)
        return envelope({
            "data": result["stdout"],
            "dry_run": dry_run if dry_run != "none" else False,
            "jsonpath_template": jsonpath_template,
        }, context, "k_patch", success=True)

    result = run_kubectl_checked(context, args, stdin=patch)
    if "error" in result:
        return envelope(result, context, "k_patch", success=False)

    # Parse and prune response
    try:
        data = json.loads(result["stdout"])
        pruned = prune(data, kind=resource_meta.kind)
        pruned = apply_output_format(pruned, output)
    except (json.JSONDecodeError, TypeError):
        pruned = {"message": result["stdout"]}

    return envelope({
        "data": pruned,
        "dry_run": dry_run if dry_run != "none" else False,
    }, context, "k_patch", success=True)
