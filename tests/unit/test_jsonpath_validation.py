"""Tests for resolution/jsonpath_validation.py — check_nested_braces (FR8)."""

from __future__ import annotations

import pytest

from src.k8s_mcp.resolution.jsonpath_validation import check_nested_braces


class TestCheckNestedBraces:
    def test_simple_field_valid(self):
        assert check_nested_braces("{.field}") is None

    def test_nested_braces_invalid(self):
        result = check_nested_braces("{.items[*].{a,b}}")
        assert result is not None
        assert "Nested braces" in result
        assert "bracket-list" in result
        assert "range" in result

    def test_deeper_nesting_invalid(self):
        result = check_nested_braces("{{{.field}}}")
        assert result is not None

    def test_sibling_blocks_valid(self):
        assert check_nested_braces("{.a}{.b}") is None

    def test_range_loop_valid(self):
        assert check_nested_braces("{range .items[*]}{.a}{end}") is None

    def test_complex_valid_template(self):
        assert check_nested_braces("{.status.podIP}{.metadata.name}") is None

    def test_empty_template_valid(self):
        assert check_nested_braces("") is None

    def test_no_braces_valid(self):
        assert check_nested_braces("just text") is None

    def test_unmatched_closing_braces_handled(self):
        assert check_nested_braces("{.field}}}") is None

    def test_only_opening_brace(self):
        assert check_nested_braces("{.field") is None
