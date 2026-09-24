"""Tests for cli.py — argument parsing."""

from __future__ import annotations

import pytest

from src.k8s_mcp.cli import (
    parse_args,
    resolve_access_level,
    resolve_allow_namespaces,
)


class TestParseArgs:
    def test_default_args(self):
        args = parse_args([])
        assert args.access_level == "readonly"
        assert args.allow_namespaces == ""

    def test_custom_access_level(self):
        args = parse_args(["--access-level", "admin"])
        assert args.access_level == "admin"

    def test_custom_allow_namespaces(self):
        args = parse_args(["--allow-namespaces", "default,kube-system"])
        assert args.allow_namespaces == "default,kube-system"

    def test_invalid_access_level(self):
        with pytest.raises(SystemExit):
            parse_args(["--access-level", "superadmin"])


class TestResolveAccessLevel:
    def test_readonly(self):
        from src.k8s_mcp.access import AccessLevel
        assert resolve_access_level("readonly") == AccessLevel.READONLY

    def test_readwrite(self):
        from src.k8s_mcp.access import AccessLevel
        assert resolve_access_level("readwrite") == AccessLevel.READWRITE

    def test_admin(self):
        from src.k8s_mcp.access import AccessLevel
        assert resolve_access_level("admin") == AccessLevel.ADMIN


class TestResolveAllowNamespaces:
    def test_empty(self):
        assert resolve_allow_namespaces("") is None
        assert resolve_allow_namespaces("  ") is None

    def test_single(self):
        assert resolve_allow_namespaces("default") == ["default"]

    def test_multiple(self):
        result = resolve_allow_namespaces("default,kube-system,kube-public")
        assert result == ["default", "kube-system", "kube-public"]

    def test_with_spaces(self):
        result = resolve_allow_namespaces(" default , kube-system ")
        assert result == ["default", "kube-system"]
