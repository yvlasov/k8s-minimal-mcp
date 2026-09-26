"""Tests for kubectl/runner.py — run_kubectl and run_kubectl_checked.

Mocks subprocess.run (not run_kubectl itself) to exercise the actual
function body that constructs base_args and delegates to subprocess.
"""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from src.k8s_mcp.kubectl.runner import run_kubectl, run_kubectl_checked


class TestRunKubectl:
    @patch("src.k8s_mcp.kubectl.runner.subprocess.run")
    def test_context_follows_kubectl(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout='{"items":[]}', stderr="", returncode=0
        )
        result = run_kubectl("my-context", ["get", "pods"])
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "kubectl"
        assert cmd[1] == "--context"
        assert cmd[2] == "my-context"

    @patch("src.k8s_mcp.kubectl.runner.subprocess.run")
    def test_context_value_matches_input(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout='{"items":[]}', stderr="", returncode=0
        )
        run_kubectl("sinsia-pl", ["get", "pods"])
        cmd = mock_run.call_args[0][0]
        assert cmd[2] == "sinsia-pl"

    @patch("src.k8s_mcp.kubectl.runner.subprocess.run")
    def test_context_two_distinct_values(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout='{"items":[]}', stderr="", returncode=0
        )
        run_kubectl("ctx-a", ["get", "pods"])
        assert mock_run.call_args[0][0][2] == "ctx-a"
        run_kubectl("ctx-b", ["get", "nodes"])
        assert mock_run.call_args[0][0][2] == "ctx-b"

    @patch("src.k8s_mcp.kubectl.runner.subprocess.run")
    def test_output_format_present_when_set(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout='{"items":[]}', stderr="", returncode=0
        )
        run_kubectl("ctx", ["get", "pods"], output_format="yaml")
        cmd = mock_run.call_args[0][0]
        assert "-o" in cmd
        idx = cmd.index("-o")
        assert cmd[idx + 1] == "yaml"

    @patch("src.k8s_mcp.kubectl.runner.subprocess.run")
    def test_output_format_omitted_when_none(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout="raw text", stderr="", returncode=0
        )
        run_kubectl("ctx", ["logs", "pod"], output_format=None)
        cmd = mock_run.call_args[0][0]
        assert "-o" not in cmd

    @patch("src.k8s_mcp.kubectl.runner.subprocess.run")
    def test_stdin_passed_through(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout='{"status":"created"}', stderr="", returncode=0
        )
        manifest = "apiVersion: v1\nkind: Pod\nmetadata:\n  name: test\n"
        run_kubectl("ctx", ["apply", "-f", "-"], stdin=manifest)
        assert mock_run.call_args[1]["input"] == manifest

    @patch("src.k8s_mcp.kubectl.runner.subprocess.run")
    def test_timeout_passed_through(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout='{"items":[]}', stderr="", returncode=0
        )
        run_kubectl("ctx", ["get", "pods"], timeout=60.0)
        assert mock_run.call_args[1]["timeout"] == 60.0

    @patch("src.k8s_mcp.kubectl.runner.subprocess.run")
    def test_success_result_shape(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout='{"items":[]}', stderr="warning", returncode=0
        )
        result = run_kubectl("ctx", ["get", "pods"])
        assert result["stdout"] == '{"items":[]}'
        assert result["stderr"] == "warning"
        assert result["returncode"] == 0
        assert result["command"][0] == "kubectl"
        assert "error" not in result

    @patch("src.k8s_mcp.kubectl.runner.subprocess.run")
    def test_timeout_expired_error(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(
            cmd="kubectl get pods", timeout=30.0
        )
        result = run_kubectl("ctx", ["get", "pods"], timeout=30.0)
        assert "error" in result
        assert "timed out" in result["error"]
        assert "30.0s" in result["error"]

    @patch("src.k8s_mcp.kubectl.runner.subprocess.run")
    def test_file_not_found_error(self, mock_run):
        mock_run.side_effect = FileNotFoundError("kubectl")
        result = run_kubectl("ctx", ["get", "pods"])
        assert "error" in result
        assert "not found" in result["error"]

    @patch("src.k8s_mcp.kubectl.runner.subprocess.run")
    def test_oserror_error(self, mock_run):
        mock_run.side_effect = OSError("permission denied")
        result = run_kubectl("ctx", ["get", "pods"])
        assert "error" in result
        assert "oserror" in result["error"]


class TestRunKubectlChecked:
    @patch("src.k8s_mcp.kubectl.runner.subprocess.run")
    def test_zero_exit_code_returns_success(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout='{"metadata":{"name":"test"}}', stderr="", returncode=0
        )
        result = run_kubectl_checked("ctx", ["get", "pods/test"])
        assert "error" not in result
        assert result["stdout"] == '{"metadata":{"name":"test"}}'

    @patch("src.k8s_mcp.kubectl.runner.map_kubectl_error")
    @patch("src.k8s_mcp.kubectl.runner.subprocess.run")
    def test_nonzero_exit_calls_map_kubectl_error(self, mock_run, mock_map):
        mock_run.return_value = MagicMock(
            stdout="", stderr="Error from server (NotFound)", returncode=1
        )
        mock_map.return_value = {"error": "object_not_found", "context": "ctx"}
        result = run_kubectl_checked("ctx", ["get", "pods/nonexistent"])
        mock_map.assert_called_once_with(
            context="ctx",
            command=mock_map.call_args[1]["command"],
            stderr="Error from server (NotFound)",
            returncode=1,
        )
        assert result["error"] == "object_not_found"

    @patch("src.k8s_mcp.kubectl.runner.subprocess.run")
    def test_timeout_error_passthrough(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(
            cmd="kubectl get pods", timeout=10.0
        )
        result = run_kubectl_checked("ctx", ["get", "pods"], timeout=10.0)
        assert "error" in result
        assert "timed out" in result["error"]

    @patch("src.k8s_mcp.kubectl.runner.subprocess.run")
    def test_file_not_found_passthrough(self, mock_run):
        mock_run.side_effect = FileNotFoundError("kubectl")
        result = run_kubectl_checked("ctx", ["get", "pods"])
        assert "error" in result
        assert "not found" in result["error"]

    @patch("src.k8s_mcp.kubectl.runner.subprocess.run")
    def test_context_preserved_through_checked(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout='{"items":[]}', stderr="", returncode=0
        )
        result = run_kubectl_checked("sinsia-pl", ["get", "pods"])
        assert "error" not in result
        assert result["command"][2] == "sinsia-pl"
