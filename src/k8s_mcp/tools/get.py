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

from ..errors import invalid_jsonpath_template, invalid_output, invalid_selector
from ..kubectl.runner import run_kubectl_checked
from ..output import apply_output_format, bound_get_names, envelope, prune
from ..resolution import DiscoveryCache, resolve, validate
from ..resolution.annotation_selector import matches_annotation_selector, parse_annotation_selector
from ..resolution.grep_filter import compile_grep_pattern, filter_lines
from ..resolution.jsonpath_validation import check_nested_braces


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
    jsonpath: str | None = None,
    annotation_selector: str | None = None,
    grep: str | None = None,
    grep_ignore_case: bool = False,
    discovery_cache: DiscoveryCache | None = None,
) -> dict[str, Any]:
    """Handle a k_get call."""
    # Fail-fast: output=jsonpath without jsonpath parameter
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
            context, "k_get", success=False,
        )

    # Fail-fast: annotation_selector + jsonpath is not supported
    if annotation_selector and jsonpath:
        return envelope(
            invalid_selector(context, annotation_selector, detail="cannot combine annotation_selector with jsonpath"),
            context, "k_get", success=False,
        )

    # Fail-fast: annotation_selector + output=wide is not supported (wide is raw kubectl
    # text output — there is no structured JSON left to filter)
    if annotation_selector and output == "wide":
        return envelope(
            invalid_selector(
                context, annotation_selector,
                detail="cannot combine annotation_selector with output=wide",
            ),
            context, "k_get", success=False,
        )

    # Fail-fast: nested-brace jsonpath (FR8)
    if jsonpath:
        nested_err = check_nested_braces(jsonpath)
        if nested_err:
            return envelope(
                invalid_jsonpath_template(context, jsonpath, detail=nested_err),
                context, "k_get", success=False,
            )

    # Fail-fast: compile grep pattern before resolve()
    grep_compiled = None
    if grep:
        grep_result = compile_grep_pattern(grep, ignore_case=grep_ignore_case)
        if isinstance(grep_result, dict):
            from ..errors import invalid_grep_pattern
            return envelope(
                invalid_grep_pattern(context, grep, detail=grep_result["error"]),
                context, "k_get", success=False,
            )
        grep_compiled = grep_result

    # Fail-fast: parse annotation_selector before resolve()
    parsed_selector: list[Any] | None = None
    if annotation_selector:
        sel_result = parse_annotation_selector(annotation_selector)
        if isinstance(sel_result, dict):
            return envelope(
                invalid_selector(context, annotation_selector, detail=sel_result["error"]),
                context, "k_get", success=False,
            )
        parsed_selector = sel_result  # type: ignore[assignment]

    # Resolve resource → GVK
    res = resolve(context, resource, discovery_cache=discovery_cache)
    if isinstance(res, dict):
        return envelope(res, context, "k_get", success=False)

    resource_meta = res

    # Pre-execution validation (R8)
    validation = validate(
        resource_meta, "get",
        namespace if not all_namespaces else None,
        all_namespaces=all_namespaces,
    )
    if validation:
        validation["context"] = context
        return envelope(validation, context, "k_get", success=False)

    # Build kubectl args
    args = ["get", resource_meta.fully_qualified_name]
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
    if jsonpath:
        result = run_kubectl_checked(context, args, output_format=f"jsonpath={jsonpath}")
        if "error" in result:
            return envelope(result, context, "k_get", success=False)
        return envelope({
            "data": result["stdout"],
            "jsonpath": jsonpath,
        }, context, "k_get", success=True)

    if output == "wide":
        result = run_kubectl_checked(context, args, output_format="wide")
        if "error" in result:
            return envelope(result, context, "k_get", success=False)
        response: dict[str, Any] = {"output": result["stdout"]}
        if grep_compiled is not None:
            filtered_text, matched, total = filter_lines(result["stdout"], grep_compiled)  # type: ignore[arg-type]
            response["output"] = filtered_text
            response["_filtered"] = {"matched": matched, "total": total}
        return envelope(response, context, "k_get", success=True)

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
