"""Tests for contexts/kubeconfig.py — list_kubeconfig_contexts.

No direct test existed for this function before — every caller-side test
mocked it away entirely. These mock subprocess.run instead, exercising the
real function body.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.k8s_mcp.contexts.kubeconfig import list_kubeconfig_contexts


class TestListKubeconfigContexts:
    @patch("src.k8s_mcp.contexts.kubeconfig.subprocess.run")
    def test_happy_path_sorted_deduped(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="context-b\ncontext-a\ncontext-a\n",
            stderr="",
        )

        result = list_kubeconfig_contexts()

        assert result == ["context-a", "context-b"]

    @patch("src.k8s_mcp.contexts.kubeconfig.subprocess.run")
    def test_calls_kubectl_with_no_kubeconfig_flag(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="ctx\n", stderr="")

        list_kubeconfig_contexts()

        called_args = mock_run.call_args[0][0]
        assert called_args == ["kubectl", "config", "get-contexts", "-o", "name"]
        assert "--kubeconfig" not in called_args

    @patch("src.k8s_mcp.contexts.kubeconfig.subprocess.run")
    def test_empty_output(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        result = list_kubeconfig_contexts()

        assert result == []

    @patch("src.k8s_mcp.contexts.kubeconfig.subprocess.run")
    def test_nonzero_exit_returns_error(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="error: no configuration has been provided"
        )

        result = list_kubeconfig_contexts()

        assert isinstance(result, dict)
        assert result["error"] == "kubectl_failure"
        assert "no configuration" in result["stderr"]

    @patch("src.k8s_mcp.contexts.kubeconfig.subprocess.run")
    def test_kubectl_not_found_returns_error(self, mock_run):
        mock_run.side_effect = FileNotFoundError("kubectl not found")

        result = list_kubeconfig_contexts()

        assert isinstance(result, dict)
        assert "error" in result
