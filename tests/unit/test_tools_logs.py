"""Tests for tools/logs.py — handle_logs."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.k8s_mcp.tools.logs import handle_logs
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


class TestHandleLogs:
    @patch("src.k8s_mcp.tools.logs.resolve")
    @patch("src.k8s_mcp.tools.logs.run_kubectl_checked")
    def test_logs_default_tail_100(self, mock_run, mock_resolve, pod_meta):
        mock_resolve.return_value = pod_meta
        mock_run.return_value = {"stdout": "log line 1\nlog line 2"}

        result = handle_logs("test-context", "mypod", namespace="default")

        assert result["success"] is True
        args = mock_run.call_args[0][1]
        assert "--tail" in args
        assert "100" in args

    @patch("src.k8s_mcp.tools.logs.resolve")
    @patch("src.k8s_mcp.tools.logs.run_kubectl_checked")
    def test_logs_explicit_tail(self, mock_run, mock_resolve, pod_meta):
        mock_resolve.return_value = pod_meta
        mock_run.return_value = {"stdout": "log line 1\nlog line 2"}

        result = handle_logs("test-context", "mypod", namespace="default", tail=10)

        assert result["success"] is True
        args = mock_run.call_args[0][1]
        tail_idx = args.index("--tail")
        assert args[tail_idx + 1] == "10"

    @patch("src.k8s_mcp.tools.logs.resolve")
    @patch("src.k8s_mcp.tools.logs.run_kubectl_checked")
    def test_logs_with_container(self, mock_run, mock_resolve, pod_meta):
        mock_resolve.return_value = pod_meta
        mock_run.return_value = {"stdout": "log line 1"}

        result = handle_logs("test-context", "mypod", namespace="default", container="sidecar")

        assert result["success"] is True
        args = mock_run.call_args[0][1]
        assert "-c" in args
        assert "sidecar" in args

    @patch("src.k8s_mcp.tools.logs.resolve")
    @patch("src.k8s_mcp.tools.logs.run_kubectl_checked")
    def test_logs_previous(self, mock_run, mock_resolve, pod_meta):
        mock_resolve.return_value = pod_meta
        mock_run.return_value = {"stdout": "previous log"}

        result = handle_logs("test-context", "mypod", namespace="default", previous=True)

        assert result["success"] is True
        args = mock_run.call_args[0][1]
        assert "--previous" in args

    @patch("src.k8s_mcp.tools.logs.resolve")
    @patch("src.k8s_mcp.tools.logs.run_kubectl_checked")
    def test_logs_since(self, mock_run, mock_resolve, pod_meta):
        mock_resolve.return_value = pod_meta
        mock_run.return_value = {"stdout": "recent log"}

        result = handle_logs("test-context", "mypod", namespace="default", since="30s")

        assert result["success"] is True
        args = mock_run.call_args[0][1]
        assert "--since" in args
        assert "30s" in args

    @patch("src.k8s_mcp.tools.logs.resolve")
    @patch("src.k8s_mcp.tools.logs.run_kubectl_checked")
    def test_logs_bound_metadata_passes_through(self, mock_run, mock_resolve, pod_meta):
        mock_resolve.return_value = pod_meta
        mock_run.return_value = {"stdout": "\n".join([f"line {i}" for i in range(150)])}

        result = handle_logs("test-context", "mypod", namespace="default", tail=100)

        assert result["success"] is True
        assert "_bound" in result["data"]
        assert result["data"]["_bound"]["truncated"] is True
        assert result["data"]["_bound"]["tail"] == 100

    @patch("src.k8s_mcp.tools.logs.resolve")
    @patch("src.k8s_mcp.tools.logs.run_kubectl_checked")
    def test_logs_no_truncation(self, mock_run, mock_resolve, pod_meta):
        mock_resolve.return_value = pod_meta
        mock_run.return_value = {"stdout": "line 1\nline 2"}

        result = handle_logs("test-context", "mypod", namespace="default", tail=100)

        assert result["data"]["_bound"]["truncated"] is False
        assert result["data"]["_bound"]["tail"] == 100

    @patch("src.k8s_mcp.tools.logs.resolve")
    def test_logs_resolve_error(self, mock_resolve, pod_meta):
        mock_resolve.return_value = {"error": "unknown_resource", "detail": "pods not found"}

        result = handle_logs("test-context", "mypod")

        assert result["success"] is False
        assert result["error"] == "unknown_resource"

    @patch("src.k8s_mcp.tools.logs.resolve")
    @patch("src.k8s_mcp.tools.logs.run_kubectl_checked")
    def test_logs_kubectl_error(self, mock_run, mock_resolve, pod_meta):
        mock_resolve.return_value = pod_meta
        mock_run.return_value = {"error": "pod_not_found", "detail": "pod mypod not found"}

        result = handle_logs("test-context", "mypod", namespace="default")

        assert result["success"] is False
        assert result["error"] == "pod_not_found"
