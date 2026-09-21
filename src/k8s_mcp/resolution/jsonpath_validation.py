"""Nested-brace detection for jsonpath_template (FR8).

Scans a jsonpath template left-to-right tracking brace depth.
If depth ever exceeds 1, the template contains nested braces
(e.g. {.items[*].{a,b}}) which is not valid Kubernetes jsonpath syntax.

This is a narrow syntactic guard — not a general jsonpath grammar validator.
"""

from __future__ import annotations


def check_nested_braces(template: str) -> str | None:
    """Return a detail string if *template* contains nested braces, else ``None``.

    Valid (depth never exceeds 1):
        ``{.field}``
        ``{.a}{.b}``  (sibling blocks)
        ``{range .items[*]}{.a}{end}``  (range loop)

    Invalid (depth exceeds 1):
        ``{.items[*].{a,b}}``  (nested braces for multi-field extraction)
        ``{{.field}}``  (double braces)
    """
    depth = 0
    for ch in template:
        if ch == "{":
            depth += 1
            if depth > 1:
                return (
                    "Nested braces are not valid Kubernetes jsonpath syntax. "
                    "For multiple fields per item use the bracket-list form "
                    "``{.items[*]['field1','field2']}`` or a "
                    "``{range .items[*]}...{end}`` loop."
                )
        elif ch == "}":
            depth -= 1
            if depth < 0:
                depth = 0
    return None
