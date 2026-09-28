"""Grep-style text filtering for unstructured-text tool output (FR14).

Provides `compile_grep_pattern()` and `filter_lines()` — the shared
implementation used by k_logs, k_describe, and k_get (output=wide).
"""

from __future__ import annotations

import re
from typing import Any


def compile_grep_pattern(pattern: str, *, ignore_case: bool = False) -> re.Pattern[str] | dict[str, Any]:
    """Compile a grep pattern into a ``re.Pattern``, or return a detail string on failure.

    Mirrors ``check_nested_braces()``'s return-``None``-or-detail-string convention
    — callers check ``isinstance(result, dict)`` to detect errors.
    """
    flags = re.IGNORECASE if ignore_case else 0
    try:
        return re.compile(pattern, flags)
    except re.error as exc:
        return {"error": f"invalid grep pattern: {exc}"}


def filter_lines(lines: list[str], compiled: re.Pattern[str]) -> tuple[list[str], int, int]:
    """Filter *lines* to those matching *compiled*, returning ``(matched_lines, matched, total)``.

    Applied identically by every caller so ``_filtered`` reporting is
    byte-for-byte consistent across tools.
    """
    total = len(lines)
    matched_lines = [line for line in lines if compiled.search(line)]
    return matched_lines, len(matched_lines), total
