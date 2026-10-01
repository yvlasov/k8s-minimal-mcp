"""k_describe tool (PRD §6, pending §13).

Delegates verbatim to `kubectl describe`. Output is verbose unstructured text.

Implemented behind a conditional flag — see server.py for registration logic.
"""

from __future__ import annotations

from typing import Any

from ..errors import invalid_selector
from ..kubectl.runner import run_kubectl_checked
from ..output import envelope
from ..resolution import DiscoveryCache, resolve, validate
from ..resolution.grep_filter import compile_grep_pattern, filter_lines


def handle_describe(
    context: str,
    resource: str,
    *,
    name: str | None = None,
    names: list[str] | None = None,
    namespace: str | None = None,
    grep: str | None = None,
    grep_ignore_case: bool = False,
    discovery_cache: DiscoveryCache | None = None,
) -> dict[str, Any]:
    """Handle a k_describe call — delegates to kubectl describe verbatim."""
    # Fail-fast: compile grep pattern before resolve()
    grep_compiled = None
    if grep:
        grep_result = compile_grep_pattern(grep, ignore_case=grep_ignore_case)
        if isinstance(grep_result, dict):
            from ..errors import invalid_grep_pattern
            return envelope(
                invalid_grep_pattern(context, grep, detail=grep_result["error"]),
                context, "k_describe", success=False,
            )
        grep_compiled = grep_result

    # Resolve resource → GVK
    res = resolve(context, resource, discovery_cache=discovery_cache)
    if isinstance(res, dict):
        return envelope(res, context, "k_describe", success=False)

    resource_meta = res

    # Pre-execution validation (R8)
    validation = validate(resource_meta, "get", namespace)
    if validation:
        validation["context"] = context
        return envelope(validation, context, "k_describe", success=False)

    # Fail-fast: exactly one of name or names must be set
    if name is None and names is None:
        return envelope(
            invalid_selector(context, resource, detail="must specify either name or names parameter"),
            context, "k_describe", success=False,
        )
    if name is not None and names is not None:
        return envelope(
            invalid_selector(context, name, detail="cannot specify both name and names parameters"),
            context, "k_describe", success=False,
        )

    # Build kubectl args
    args = ["describe", resource_meta.fully_qualified_name]
    if name:
        args.append(name)
    elif names:
        args.extend(names)
    if namespace:
        args.extend(["-n", namespace])

    # Execute — describe outputs text, not JSON (output_format=None omits -o flag)
    result = run_kubectl_checked(context, args, output_format=None)
    if "error" in result:
        return envelope(result, context, "k_describe", success=False)

    response: dict[str, Any] = {
        "output": result["stdout"].splitlines(),
    }

    # Apply grep filter to the output text field only
    if grep_compiled is not None:
        filtered_lines, matched, total = filter_lines(result["stdout"].splitlines(), grep_compiled)
        response["output"] = filtered_lines
        response["_filtered"] = {"matched": matched, "total": total}

    return envelope(response, context, "k_describe", success=True)
