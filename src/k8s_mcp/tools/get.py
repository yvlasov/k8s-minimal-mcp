"""k_get tool (PRD §6).

GET a Kubernetes resource by type and name.

Required: context, resource
Optional: name, namespace, all_namespaces, label_selector, field_selector, output

Default: output=name (names only). Full JSON on request.
All JSON responses are field-pruned per R9.
"""

from __future__ import annotations

import json
from typing import Any

from ..resolution import resolve, validate, DiscoveryCache
from ..resolution.annotation_selector import parse_annotation_selector, matches_annotation_selector
from ..resolution.jsonpath_validation import check_nested_braces
from ..kubectl.runner import run_kubectl_checked
from ..output import prune, bound_get_names, apply_output_format, envelope
from ..errors import unknown_context, invalid_output, invalid_selector, invalid_jsonpath_template


def handle_get(
    context: str,
    resource: str,
    *,
    name: str | None = None,
    namespace: str | None = None,
    all_namespaces: bool = False,
    label_selector: str | None = None,
    field_selector: str | None = None,
    output: str | None = None,
    jsonpath_template: str | None = None,
    annotation_selector: str | None = None,
    discovery_cache: DiscoveryCache | None = None,
) -> dict[str, Any]:
    """Handle a k_get call."""
    # Fail-fast: output=jsonpath without template
    if output == "jsonpath" and not jsonpath_template:
        return envelope(
            invalid_output(context, output),
            context, "k_get", success=False,
        )

    # Fail-fast: annotation_selector + jsonpath_template is not supported
    if annotation_selector and jsonpath_template:
        return envelope(
            invalid_selector(context, annotation_selector, detail="cannot combine annotation_selector with jsonpath_template"),
            context, "k_get", success=False,
        )

    # Fail-fast: annotation_selector + output=wide is not supported (wide is raw kubectl
    # text output — there is no structured JSON left to filter)
    if annotation_selector and output == "wide":
        return envelope(
            invalid_selector(context, annotation_selector, detail="cannot combine annotation_selector with output=wide"),
            context, "k_get", success=False,
        )

    # Fail-fast: nested-brace jsonpath_template (FR8)
    if jsonpath_template:
        nested_err = check_nested_braces(jsonpath_template)
        if nested_err:
            return envelope(
                invalid_jsonpath_template(context, jsonpath_template, detail=nested_err),
                context, "k_get", success=False,
            )

    # Fail-fast: parse annotation_selector before resolve()
    parsed_selector: list[Any] | None = None
    if annotation_selector:
        sel_result = parse_annotation_selector(annotation_selector)
        if isinstance(sel_result, dict) and "error" in sel_result:
            return envelope(
                invalid_selector(context, annotation_selector, detail=sel_result["error"]),
                context, "k_get", success=False,
            )
        parsed_selector = sel_result  # type: ignore[assignment]

    # Resolve resource → GVK
    res = resolve(context, resource, discovery_cache=discovery_cache)
    if isinstance(res, dict) and "error" in res:
        return envelope(res, context, "k_get", success=False)

    resource_meta = res

    # Pre-execution validation (R8)
    validation = validate(resource_meta, "get", namespace if not all_namespaces else None, all_namespaces=all_namespaces)
    if validation:
        validation["context"] = context
        return envelope(validation, context, "k_get", success=False)

    # Build kubectl args
    args = ["get", resource_meta.canonical]
    if name and not all_namespaces:
        args.append(name)
    if namespace and not all_namespaces:
        args.extend(["-n", namespace])
    if all_namespaces:
        args.append("--all-namespaces")
    if label_selector:
        args.extend(["-l", label_selector])
    if field_selector:
        args.extend(["--field-selector", field_selector])

    # Execute
    if jsonpath_template:
        result = run_kubectl_checked(context, args, output_format=f"jsonpath={jsonpath_template}")
        if "error" in result:
            return envelope(result, context, "k_get", success=False)
        return envelope({
            "data": result["stdout"],
            "jsonpath_template": jsonpath_template,
        }, context, "k_get", success=True)

    if output == "wide":
        result = run_kubectl_checked(context, args, output_format="wide")
        if "error" in result:
            return envelope(result, context, "k_get", success=False)
        return envelope({"output": result["stdout"]}, context, "k_get", success=True)

    result = run_kubectl_checked(context, args)
    if "error" in result:
        return envelope(result, context, "k_get", success=False)

    # Parse JSON
    try:
        data = json.loads(result["stdout"])
    except json.JSONDecodeError:
        return envelope(
            {"error": "unexpected kubectl output (not JSON)", "raw": result["stdout"]},
            context, "k_get", success=False,
        )

    # Filter by annotation_selector if set
    filtered_meta: dict[str, Any] | None = None
    if parsed_selector:
        is_list = "items" in data
        items = data["items"] if is_list else [data]
        total = len(items)
        filtered = [
            item for item in items
            if matches_annotation_selector(item.get("metadata", {}).get("annotations", {}), parsed_selector)
        ]
        filtered_meta = {"matched": len(filtered), "total": total}
        if is_list:
            data = {**data, "items": filtered}
        elif filtered:
            data = filtered[0]  # single resource matched — keep it as the resource itself
        else:
            data = {"kind": "List", "items": []}  # single resource didn't match — empty result

    # Output shaping
    keep_status = output in ("json", "yaml", "wide") if output else False
    pruned = prune(data, kind=resource_meta.kind, keep_status=keep_status)

    if output is None:
        # Default: name-only output (R10)
        pruned = bound_get_names(pruned)
        if filtered_meta:
            pruned["_filtered"] = filtered_meta
    else:
        pruned = apply_output_format(pruned, output)
        if filtered_meta and output != "wide":
            if isinstance(pruned, dict):
                pruned["_filtered"] = filtered_meta

    return envelope(pruned, context, "k_get", success=True)
