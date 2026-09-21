"""Tests for tools/exec_.py — handle_exec."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.k8s_mcp.tools.exec_ import handle_exec
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


class TestHandleExec:
    @patch("src.k8s_mcp.tools.exec_.resolve")
    @patch("src.k8s_mcp.tools.exec_.run_kubectl_checked")
    def test_exec_with_container(self, mock_run, mock_resolve, pod_meta):
        mock_resolve.return_value = pod_meta
        mock_run.return_value = {"stdout": "", "stderr": "", "returncode": 0}

        result = handle_exec("test-context", "mypod", ["ls", "-l"], namespace="default", container="sidecar")

        assert result["success"] is True
        args = mock_run.call_args[0][1]
        assert args == ["exec", "mypod", "-c", "sidecar", "--", "ls", "-l"]

    @patch("src.k8s_mcp.tools.exec_.resolve")
    @patch("src.k8s_mcp.tools.exec_.run_kubectl_checked")
    def test_exec_without_container(self, mock_run, mock_resolve, pod_meta):
        mock_resolve.return_value = pod_meta
        mock_run.return_value = {"stdout": "", "stderr": "", "returncode": 0}

        result = handle_exec("test-context", "mypod", ["ls", "-l"], namespace="default")

        assert result["success"] is True
        args = mock_run.call_args[0][1]
        assert args == ["exec", "mypod", "--", "ls", "-l"]

    @patch("src.k8s_mcp.tools.exec_.resolve")
    @patch("src.k8s_mcp.tools.exec_.run_kubectl_checked")
    def test_exec_output_format_none(self, mock_run, mock_resolve, pod_meta):
        mock_resolve.return_value = pod_meta
        mock_run.return_value = {"stdout": "", "stderr": "", "returncode": 0}

        handle_exec("test-context", "mypod", ["ls"], namespace="default")

        assert mock_run.call_args[1]["output_format"] is None

    @patch("src.k8s_mcp.tools.exec_.resolve")
    @patch("src.k8s_mcp.tools.exec_.run_kubectl_checked")
    def test_exec_success_shape(self, mock_run, mock_resolve, pod_meta):
        mock_resolve.return_value = pod_meta
        mock_run.return_value = {"stdout": "file1\nfile2", "stderr": "", "returncode": 0}

        result = handle_exec("test-context", "mypod", ["ls"], namespace="default")

        assert result["success"] is True
        assert result["data"]["stdout"] == "file1\nfile2"
        assert result["data"]["stderr"] == ""
        assert result["data"]["exit_code"] == 0

    @patch("src.k8s_mcp.tools.exec_.resolve")
    @patch("src.k8s_mcp.tools.exec_.run_kubectl_checked")
    def test_exec_kubectl_failure_becomes_exec_failed(self, mock_run, mock_resolve, pod_meta):
        mock_resolve.return_value = pod_meta
        mock_run.return_value = {
            "error": "kubectl_failure",
            "stderr": "error: execution failed",
            "exit_code": 1,
        }

        result = handle_exec("test-context", "mypod", ["ls"], namespace="default")

        assert result["success"] is False
        assert result["error"] == "exec_failed"
        assert result["pod"] == "mypod"
        assert result["namespace"] == "default"
        assert result["exit_code"] == 1

    @patch("src.k8s_mcp.tools.exec_.resolve")
    @patch("src.k8s_mcp.tools.exec_.run_kubectl_checked")
    def test_exec_other_error_passthrough(self, mock_run, mock_resolve, pod_meta):
        mock_resolve.return_value = pod_meta
        mock_run.return_value = {"error": "access_denied", "detail": "forbidden"}

        result = handle_exec("test-context", "mypod", ["ls"], namespace="default")

        assert result["success"] is False
        assert result["error"] == "access_denied"

    @patch("src.k8s_mcp.tools.exec_.resolve")
    def test_exec_resolve_error(self, mock_resolve, pod_meta):
        mock_resolve.return_value = {"error": "unknown_resource", "detail": "pods not found"}

        result = handle_exec("test-context", "mypod", ["ls"])

        assert result["success"] is False
        assert result["error"] == "unknown_resource"
