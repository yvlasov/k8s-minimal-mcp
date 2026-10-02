"""Tests for resolution/grep_filter.py — compile_grep_pattern and filter_lines (FR14)."""

from __future__ import annotations

import re

from src.k8s_mcp.resolution.grep_filter import compile_grep_pattern, filter_lines


class TestCompileGrepPattern:
    def test_valid_simple_pattern(self):
        result = compile_grep_pattern("error")
        assert isinstance(result, re.Pattern)
        assert result.pattern == "error"

    def test_valid_regex_pattern(self):
        result = compile_grep_pattern(r"\d+\.\d+\.\d+")
        assert isinstance(result, re.Pattern)

    def test_invalid_regex_returns_error_dict(self):
        result = compile_grep_pattern("[invalid")
        assert isinstance(result, dict)
        assert "error" in result
        assert "invalid grep pattern" in result["error"]

    def test_ignore_case_flag(self):
        result = compile_grep_pattern("ERROR", ignore_case=True)
        assert isinstance(result, re.Pattern)
        assert result.flags & re.IGNORECASE

    def test_ignore_case_false(self):
        result = compile_grep_pattern("ERROR", ignore_case=False)
        assert isinstance(result, re.Pattern)
        assert not (result.flags & re.IGNORECASE)


class TestFilterLines:
    def test_filters_matching_lines(self):
        lines = ["line 1", "error here", "line 3", "another error"]
        pattern = re.compile("error")
        filtered, matched, total = filter_lines(lines, pattern)
        assert filtered == ["error here", "another error"]
        assert matched == 2
        assert total == 4

    def test_no_matches(self):
        lines = ["line 1", "line 2", "line 3"]
        pattern = re.compile("notfound")
        filtered, matched, total = filter_lines(lines, pattern)
        assert filtered == []
        assert matched == 0
        assert total == 3

    def test_all_match(self):
        lines = ["error1", "error2", "error3"]
        pattern = re.compile("error")
        filtered, matched, total = filter_lines(lines, pattern)
        assert filtered == lines
        assert matched == 3
        assert total == 3

    def test_empty_input(self):
        pattern = re.compile("anything")
        filtered, matched, total = filter_lines([], pattern)
        assert filtered == []
        assert matched == 0
        assert total == 0

    def test_single_line(self):
        lines = ["only line"]
        pattern = re.compile("only")
        filtered, matched, total = filter_lines(lines, pattern)
        assert filtered == ["only line"]
        assert matched == 1
        assert total == 1

    def test_multiline_preserves_order(self):
        lines = ["a", "b", "c", "d", "e"]
        pattern = re.compile("[bd]")
        filtered, matched, total = filter_lines(lines, pattern)
        assert filtered == ["b", "d"]
        assert matched == 2
        assert total == 5
