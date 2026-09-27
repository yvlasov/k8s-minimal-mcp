"""Tests for resolution/grep_filter.py — compile_grep_pattern and filter_lines (FR14)."""

from __future__ import annotations

import re

import pytest

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
        text = "line 1\nerror here\nline 3\nanother error"
        pattern = re.compile("error")
        filtered, matched, total = filter_lines(text, pattern)
        assert filtered == "error here\nanother error"
        assert matched == 2
        assert total == 4

    def test_no_matches(self):
        text = "line 1\nline 2\nline 3"
        pattern = re.compile("notfound")
        filtered, matched, total = filter_lines(text, pattern)
        assert filtered == ""
        assert matched == 0
        assert total == 3

    def test_all_match(self):
        text = "error1\nerror2\nerror3"
        pattern = re.compile("error")
        filtered, matched, total = filter_lines(text, pattern)
        assert filtered == text
        assert matched == 3
        assert total == 3

    def test_empty_input(self):
        pattern = re.compile("anything")
        filtered, matched, total = filter_lines("", pattern)
        assert filtered == ""
        assert matched == 0
        assert total == 0

    def test_single_line(self):
        text = "only line"
        pattern = re.compile("only")
        filtered, matched, total = filter_lines(text, pattern)
        assert filtered == "only line"
        assert matched == 1
        assert total == 1

    def test_multiline_preserves_order(self):
        text = "a\nb\nc\nd\ne"
        pattern = re.compile("[bd]")
        filtered, matched, total = filter_lines(text, pattern)
        assert filtered == "b\nd"
        assert matched == 2
        assert total == 5
