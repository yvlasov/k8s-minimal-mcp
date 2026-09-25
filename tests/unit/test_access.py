"""Tests for access.py — R7 registration filtering per level."""

from __future__ import annotations

import pytest

from src.k8s_mcp.access import AccessLevel, allowed_verbs, tool_for_verb


class TestAccessLevel:
    def test_readonly_verbs(self):
        verbs = allowed_verbs(AccessLevel.READONLY)
        assert verbs == frozenset({"get", "logs", "describe", "list_resources", "get_helm_release", "auth_can_i"})

    def test_readwrite_verbs(self):
        verbs = allowed_verbs(AccessLevel.READWRITE)
        assert verbs == frozenset({"get", "logs", "describe", "list_resources", "get_helm_release", "auth_can_i", "apply", "patch", "delete"})

    def test_admin_verbs(self):
        verbs = allowed_verbs(AccessLevel.ADMIN)
        assert verbs == frozenset({"get", "logs", "describe", "list_resources", "get_helm_release", "auth_can_i", "apply", "patch", "delete", "exec", "get_secret_to_file"})

    def test_readonly_excludes_mutating(self):
        readonly = allowed_verbs(AccessLevel.READONLY)
        assert "apply" not in readonly
        assert "patch" not in readonly
        assert "delete" not in readonly

    def test_readwrite_excludes_exec(self):
        readwrite = allowed_verbs(AccessLevel.READWRITE)
        assert "exec" not in readwrite
        assert "get_secret_to_file" not in readwrite

    def test_admin_includes_all(self):
        admin = allowed_verbs(AccessLevel.ADMIN)
        assert len(admin) == 11

    def test_readonly_includes_describe(self):
        readonly = allowed_verbs(AccessLevel.READONLY)
        assert "describe" in readonly


class TestToolForVerb:
    def test_tool_name_get(self):
        assert tool_for_verb("get") == "k_get"

    def test_tool_name_logs(self):
        assert tool_for_verb("logs") == "k_logs"

    def test_tool_name_apply(self):
        assert tool_for_verb("apply") == "k_apply"

    def test_tool_name_patch(self):
        assert tool_for_verb("patch") == "k_patch"

    def test_tool_name_delete(self):
        assert tool_for_verb("delete") == "k_delete"

    def test_tool_name_exec(self):
        assert tool_for_verb("exec") == "k_exec"

    def test_tool_name_describe(self):
        assert tool_for_verb("describe") == "k_describe"
