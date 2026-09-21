"""k_apply tool (PRD §6).

Apply a manifest to a resource.

Required: context, manifest
Optional: namespace, dry_run

Response states dry_run status.
"""

from __future__ import annotations

import json
from typing import Any

from ..resolution import resolve, validate, DiscoveryCache
from ..resolution.jsonpath_validation import check_nested_braces
from ..kubectl.runner import run_kubectl_checked
from ..output import prune, envelope, apply_output_format
from ..errors import unknown_resource, invalid_manifest, invalid_output, invalid_jsonpath_template


def _parse_manifest(manifest: str) -> dict[str, Any]:
    """Parse a JSON or YAML manifest string."""
    # Try JSON first
    try:
        return json.loads(manifest)
    except json.JSONDecodeError:
        pass

    # Try YAML
    try:
        import yaml
        return yaml.safe_load(manifest)
    except ImportError:
        pass
    except Exception:
        pass

    return {}


def handle_apply(
    context: str,
    manifest: str,
    *,
    namespace: str | None = None,
    dry_run: str = "none",  # "none", "client", "server"
    output: str | None = None,
    jsonpath_template: str | None = None,
    discovery_cache: DiscoveryCache | None = None,
) -> dict[str, Any]:
    """Handle a k_apply call."""
    # Fail-fast: output=jsonpath without template
    if output == "jsonpath" and not jsonpath_template:
        return envelope(
            invalid_output(context, output),
            context, "k_apply", success=False,
        )

    # Fail-fast: output=wide not supported on apply (kubectl's -o wide has no meaning for apply/patch)
    if output == "wide":
        return envelope(
            invalid_output(context, output),
            context, "k_apply", success=False,
        )

    # Fail-fast: nested-brace jsonpath_template (FR8)
    if jsonpath_template:
        nested_err = check_nested_braces(jsonpath_template)
        if nested_err:
            return envelope(
                invalid_jsonpath_template(context, jsonpath_template, detail=nested_err),
                context, "k_apply", success=False,
            )

    # Parse manifest to determine resource type for validation
    manifest_data = _parse_manifest(manifest)

    if not isinstance(manifest_data, dict) or not manifest_data:
        return envelope(
            invalid_manifest(context, detail="manifest is empty or invalid"),
            context, "k_apply", success=False,
        )

    kind = manifest_data.get("kind", "")
    if not kind:
        return envelope(
            invalid_manifest(context, detail="manifest missing 'kind' field"),
            context, "k_apply", success=False,
        )

    # Resolve kind → GVK for validation (R8)
    res = resolve(context, kind, discovery_cache=discovery_cache)
    if isinstance(res, dict) and "error" in res:
        return envelope(res, context, "k_apply", success=False)

    resource_meta = res

    # Pre-execution validation (R8)
    validation = validate(resource_meta, "apply", namespace)
    if validation:
        validation["context"] = context
        return envelope(validation, context, "k_apply", success=False)

    # Build kubectl args
    args = ["apply", "-f", "-"]
    if namespace:
        args.extend(["-n", namespace])
    if dry_run != "none":
        args.extend(["--dry-run", dry_run])

    # Execute
    if jsonpath_template:
        result = run_kubectl_checked(context, args, stdin=manifest, output_format=f"jsonpath={jsonpath_template}")
        if "error" in result:
            return envelope(result, context, "k_apply", success=False)
        return envelope({
            "data": result["stdout"],
            "dry_run": dry_run if dry_run != "none" else False,
            "jsonpath_template": jsonpath_template,
        }, context, "k_apply", success=True)

    result = run_kubectl_checked(context, args, stdin=manifest)
    if "error" in result:
        return envelope(result, context, "k_apply", success=False)

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
    }, context, "k_apply", success=True)
