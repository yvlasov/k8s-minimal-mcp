"""Annotation selector parsing and matching for FR2.

Parses the `key=value` / `key!=value` / bare-`key` grammar from PRD FR2
and applies it against `metadata.annotations` dicts with AND semantics.
"""

from __future__ import annotations

import re
from typing import Any


# Regex for a single term: key=value, key!=value, or bare key
# Key: starts with letter/digit, may contain letters/digits/-/_/.
# Value: any non-comma characters (simplified — real k8s allows more)
_TERM_RE = re.compile(
    r'^([A-Za-z0-9][A-Za-z0-9/_-]*)(!=)(.+)$'   # key!=value
    r'|^([A-Za-z0-9][A-Za-z0-9/_-]*)=(.+)$'      # key=value
    r'|^([A-Za-z0-9][A-Za-z0-9/_-]*)$'            # bare key
)

# Split on commas, but respect quoted values (simplified — no nested quotes)
_TERM_SPLIT_RE = re.compile(r',(?=(?:[^"]*"[^"]*")*[^"]*$)')


class _Term:
    """A single annotation selector term."""
    __slots__ = ("key", "op", "value")

    def __init__(self, key: str, op: str, value: str):
        self.key = key
        self.op = op
        self.value = value

    def __repr__(self) -> str:
        return f"_Term({self.key!r}, {self.op!r}, {self.value!r})"


def parse_annotation_selector(selector: str) -> list[_Term] | dict[str, Any]:
    """Parse an annotation selector string into a list of terms.

    Grammar:
        selector = term ("," term)*
        term     = key "=" value | key "!=" value | key
        key      = [a-zA-Z0-9][a-zA-Z0-9/_-]*
        value    = any non-empty string (no comma splitting beyond the top level)

    Returns a list of _Term tuples (key, op, value) where op is "=", "!=", or "".
    On malformed syntax, returns a dict with "error" key.
    """
    if not selector or not selector.strip():
        return {"error": "annotation_selector cannot be empty"}

    terms: list[_Term] = []
    raw_terms = _TERM_SPLIT_RE.split(selector)

    for raw in raw_terms:
        raw = raw.strip()
        if not raw:
            return {"error": "annotation_selector contains empty term (trailing comma?)"}

        m = _TERM_RE.match(raw)
        if not m:
            return {"error": f"annotation_selector: invalid term syntax: {raw!r}"}

        if m.group(6) is not None:
            # Bare key (existence check)
            terms.append(_Term(key=m.group(6), op="", value=""))
        elif m.group(4) is not None:
            # key=value
            key = m.group(4)
            value = m.group(5)
            terms.append(_Term(key=key, op="=", value=value))
        else:
            # key!=value
            key = m.group(1)
            value = m.group(3)
            terms.append(_Term(key=key, op="!=", value=value))

    return terms


def matches_annotation_selector(annotations: dict[str, Any], terms: list[_Term] | list[dict[str, Any]]) -> bool:
    """Check if annotations match all parsed terms (AND semantics).

    Each term must match for the result to be True.
    - op="": key must exist in annotations (any value)
    - op="=": key must exist and annotations[key] == value
    - op="!=": key must exist and annotations[key] != value

    Handles both _Term objects and dict representations (for JSON-deserialized cases).
    """
    if not terms:
        return True

    for term in terms:
        if isinstance(term, dict):
            key = term.get("key", "")
            op = term.get("op", "")
            value = term.get("value", "")
        else:
            key = term.key
            op = term.op
            value = term.value

        ann_val = annotations.get(key)

        if op == "":
            # Existence check
            if key not in annotations:
                return False
        elif op == "=":
            # Equality
            if ann_val is None or str(ann_val) != value:
                return False
        elif op == "!=":
            # Inequality
            if ann_val is None or str(ann_val) == value:
                return False
        else:
            # Unknown op — treat as non-match
            return False

    return True
