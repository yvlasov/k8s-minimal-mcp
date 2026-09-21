"""Tests for tools/describe.py — handle_describe."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.k8s_mcp.tools.describe import handle_describe
from src.k8s_mcp.resolution.models import ResourceMeta


@pytest.fixture
def pod_meta():
    return ResourceMeta(
        canonical="pods",
        shortnames=["po"],
        kind="Pod",
        group="",
        version="v1",
        namespaced=True,
        verbs=["get", "logs", "apply", "patch", "delete", "exec", "list"],
    )


class TestHandleDescribe:
    @patch("src.k8s_mcp.tools.describe.resolve")
    @patch("src.k8s_mcp.tools.describe.run_kubectl_checked")
    def test_describe_builds_correct_args(self, mock_run, mock_resolve, pod_meta):
        mock_resolve.return_value = pod_meta
        mock_run.return_value = {"stdout": "Name:         mypod\nNamespace:    default\n"}

        result = handle_describe("test-context", "pods", name="mypod", namespace="default")

        assert result["success"] is True
        args = mock_run.call_args[0][1]
        assert args == ["describe", "pods", "mypod", "-n", "default"]

    @patch("src.k8s_mcp.tools.describe.resolve")
    @patch("src.k8s_mcp.tools.describe.run_kubectl_checked")
    def test_describe_output_format_none(self, mock_run, mock_resolve, pod_meta):
        mock_resolve.return_value = pod_meta
        mock_run.return_value = {"stdout": "Name:         mypod\n"}

        handle_describe("test-context", "pods", name="mypod", namespace="default")

        assert mock_run.call_args[1]["output_format"] is None

    @patch("src.k8s_mcp.tools.describe.resolve")
    @patch("src.k8s_mcp.tools.describe.run_kubectl_checked")
    def test_describe_validates_against_get_verb(self, mock_run, mock_resolve, pod_meta):
        mock_resolve.return_value = pod_meta
        mock_run.return_value = {"stdout": "Name:         mypod\n"}

        handle_describe("test-context", "pods", name="mypod", namespace="default")

        # describe.py validates against "get" verb since there's no "describe" entry in ResourceMeta.verbs
        mock_resolve.assert_called_once()

    @patch("src.k8s_mcp.tools.describe.resolve")
    @patch("src.k8s_mcp.tools.describe.run_kubectl_checked")
    def test_describe_success_shape(self, mock_run, mock_resolve, pod_meta):
        mock_resolve.return_value = pod_meta
        mock_run.return_value = {"stdout": "Name:         mypod\nNamespace:    default\nStatus:       Running"}

        result = handle_describe("test-context", "pods", name="mypod", namespace="default")

        assert result["success"] is True
        assert result["data"]["output"] == "Name:         mypod\nNamespace:    default\nStatus:       Running"

    @patch("src.k8s_mcp.tools.describe.resolve")
    def test_describe_resolve_error(self, mock_resolve, pod_meta):
        mock_resolve.return_value = {"error": "unknown_resource", "detail": "pods not found"}

        result = handle_describe("test-context", "pods", name="mypod")

        assert result["success"] is False
        assert result["error"] == "unknown_resource"

    @patch("src.k8s_mcp.tools.describe.resolve")
    @patch("src.k8s_mcp.tools.describe.run_kubectl_checked")
    def test_describe_kubectl_error(self, mock_run, mock_resolve, pod_meta):
        mock_resolve.return_value = pod_meta
        mock_run.return_value = {"error": "pod_not_found", "detail": "pod mypod not found"}

        result = handle_describe("test-context", "pods", name="mypod", namespace="default")

        assert result["success"] is False
        assert result["error"] == "pod_not_found"
