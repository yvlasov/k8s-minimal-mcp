"""Tests for kubectl stderr → error code mapping (PRD §7)."""

import pytest

from src.k8s_mcp.kubectl.errors import map_kubectl_error


class TestMapKubectlError:
    """Test map_kubectl_error maps kubectl stderr patterns correctly."""

    def test_ambiguous_resource(self):
        result = map_kubectl_error(
            context="test",
            command=["kubectl", "get", "pods"],
            stderr="Ambiguous resource (please specify the fully qualified name)",
            returncode=1,
        )
        assert result["error"] == "ambiguous_resource"
        assert result["context"] == "test"
        assert "Ambiguous" in result["raw_stderr"]

    def test_not_found(self):
        result = map_kubectl_error(
            context="test",
            command=["kubectl", "get", "pods/x"],
            stderr='pods "x" not found',
            returncode=1,
        )
        assert result["error"] == "unknown_resource"
        assert result["context"] == "test"
        assert 'pods "x" not found' in result["raw_stderr"]

    def test_not_found_uppercase(self):
        result = map_kubectl_error(
            context="test",
            command=["kubectl", "get", "pods/x"],
            stderr='Error from server (NotFound): pods "x" not found',
            returncode=1,
        )
        assert result["error"] == "unknown_resource"

    def test_forbidden(self):
        result = map_kubectl_error(
            context="test",
            command=["kubectl", "apply", "-f", "-"],
            stderr='error: forbidden: user "admin" is forbidden',
            returncode=1,
        )
        assert result["error"] == "access_denied"
        assert result["context"] == "test"

    def test_unauthorized(self):
        result = map_kubectl_error(
            context="test",
            command=["kubectl", "get", "pods"],
            stderr='Unauthorized',
            returncode=1,
        )
        assert result["error"] == "access_denied"
        assert result["context"] == "test"

    def test_default_kubectl_failure(self):
        result = map_kubectl_error(
            context="test",
            command=["kubectl", "get", "customresourcedefinitions"],
            stderr='the server disagrees with pods, trying to create',
            returncode=1,
        )
        assert result["error"] == "kubectl_failure"
        assert result["context"] == "test"
        assert "the server disagrees" in result["stderr"]
        assert result["exit_code"] == 1
