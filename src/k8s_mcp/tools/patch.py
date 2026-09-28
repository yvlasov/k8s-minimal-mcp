"""k_patch tool (PRD §6).

Patch a Kubernetes resource.

Required: context, resource, name, patch
Optional: namespace, type (strategic/merge/json), dry_run
"""

from __future__ import annotations

import json
from typing import Any

from ..errors import invalid_jsonpath_template, invalid_output
from ..kubectl.runner import run_kubectl_checked
from ..output import apply_output_format, envelope, prune
from ..resolution import DiscoveryCache, resolve, validate
from ..resolution.jsonpath_validation import check_nested_braces


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
    jsonpath: str | None = None,
    discovery_cache: DiscoveryCache | None = None,
) -> dict[str, Any]:
    """Handle a k_patch call."""
    # Fail-fast: output=jsonpath is no longer valid — jsonpath param alone is the trigger
    if output == "jsonpath" and not jsonpath:
        return envelope(
            invalid_output(
                context, output,
                detail=(
                    "'jsonpath' is no longer a valid output value — set the jsonpath "
                    "parameter directly instead, e.g. jsonpath='{.metadata.name}'. "
                    "output does not need to be set when jsonpath is."
                ),
            ),
            context, "k_patch", success=False,
        )

    # Fail-fast: nested-brace jsonpath (FR8)
    if jsonpath:
        nested_err = check_nested_braces(jsonpath)
        if nested_err:
            return envelope(
                invalid_jsonpath_template(context, jsonpath, detail=nested_err),
                context, "k_patch", success=False,
            )

    # Fail-fast: output=wide not supported on patch (kubectl's -o wide has no meaning for apply/patch)
    # Only fires when jsonpath is not set — jsonpath unconditionally overrides output (FR20)
    if not jsonpath and output == "wide":
        return envelope(
            invalid_output(
                context, output,
                detail=(
                    "output=wide has no meaning for k_patch — "
                    "kubectl's -o wide is a get-only list-formatting flag"
                ),
            ),
            context, "k_patch", success=False,
        )

    # Resolve resource → GVK
    res = resolve(context, resource, discovery_cache=discovery_cache)
    if isinstance(res, dict):
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
    if jsonpath:
        result = run_kubectl_checked(context, args, stdin=patch, output_format=f"jsonpath={jsonpath}")
        if "error" in result:
            return envelope(result, context, "k_patch", success=False)
        return envelope({
            "data": result["stdout"],
            "dry_run": dry_run if dry_run != "none" else False,
            "jsonpath": jsonpath,
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
