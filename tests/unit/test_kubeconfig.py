"""Tests for contexts/kubeconfig.py — list_kubeconfig_contexts.

Issue 57: the function now runs through kubectl/runner.py — the project's
single subprocess seam. These exercise the real function body with the runner
mocked, the same way every other tool's tests mock the seam (the pre-57
version mocked subprocess.run directly, which only existed because it bypassed
the seam). Timeout/FileNotFoundError/OSError mapping lives in the runner and
is covered by test_runner.py (Issue 47) — not re-mocked here.
"""

from __future__ import annotations

from unittest.mock import patch

from src.k8s_mcp.contexts.kubeconfig import list_kubeconfig_contexts

_OK = {"stderr": "", "returncode": 0, "command": ["kubectl"]}


class TestListKubeconfigContexts:
    @patch("src.k8s_mcp.contexts.kubeconfig.run_kubectl_checked")
    def test_happy_path_sorted_deduped(self, mock_run):
        mock_run.return_value = {"stdout": "context-b\ncontext-a\ncontext-a\n", **_OK}

        result = list_kubeconfig_contexts()

        assert result == ["context-a", "context-b"]

    @patch("src.k8s_mcp.contexts.kubeconfig.run_kubectl_checked")
    def test_runs_through_runner_with_name_format(self, mock_run):
        mock_run.return_value = {"stdout": "ctx\n", **_OK}

        list_kubeconfig_contexts("my-context")

        # No --kubeconfig anywhere: the runner's own no-kubeconfig policy (Issue 33)
        # now covers this call site too.
        mock_run.assert_called_once_with(
            "my-context", ["config", "get-contexts"], output_format="name",
        )

    @patch("src.k8s_mcp.contexts.kubeconfig.run_kubectl_checked")
    def test_empty_output(self, mock_run):
        mock_run.return_value = {"stdout": "", **_OK}

        result = list_kubeconfig_contexts()

        assert result == []

    @patch("src.k8s_mcp.contexts.kubeconfig.run_kubectl_checked")
    def test_blank_lines_filtered(self, mock_run):
        mock_run.return_value = {"stdout": "ctx-b\n\n  \nctx-a\n", **_OK}

        result = list_kubeconfig_contexts()

        assert result == ["ctx-a", "ctx-b"]

    @patch("src.k8s_mcp.contexts.kubeconfig.run_kubectl_checked")
    def test_runner_error_dict_returned_verbatim(self, mock_run):
        # Non-zero exits arrive already mapped to §7 shape (code + context) by
        # run_kubectl_checked — the kubeconfig layer must pass them through unchanged.
        mock_run.return_value = {
            "error": "kubectl_failure", "context": "c",
            "raw_stderr": "error: no configuration has been provided",
        }

        result = list_kubeconfig_contexts("c")

        assert isinstance(result, dict)
        assert result["error"] == "kubectl_failure"
        assert result["context"] == "c"
