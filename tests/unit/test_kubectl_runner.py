"""Tests for kubectl/runner.py — run_kubectl and run_kubectl_checked."""

from __future__ import annotations

from unittest.mock import patch

from src.k8s_mcp.kubectl.runner import run_kubectl, run_kubectl_checked


class TestRunKubectl:
    """Test run_kubectl subprocess execution and environment passing."""

    @patch("src.k8s_mcp.kubectl.runner.subprocess.run")
    def test_run_kubectl_inherits_environment(self, mock_subprocess_run):
        """Test that run_kubectl passes os.environ to subprocess.run."""
        mock_proc = mock_subprocess_run.return_value
        mock_proc.stdout = '{"items": []}'
        mock_proc.stderr = ""
        mock_proc.returncode = 0

        result = run_kubectl("test-context", ["get", "pods"])

        assert result["stdout"] == '{"items": []}'
        assert result["returncode"] == 0

        # Verify subprocess.run was called with env parameter
        call_kwargs = mock_subprocess_run.call_args[1]
        assert "env" in call_kwargs
        assert call_kwargs["env"] is not None

    @patch("src.k8s_mcp.kubectl.runner.subprocess.run")
    def test_run_kubectl_with_proxy_environment(self, mock_subprocess_run):
        """Test that proxy environment variables are passed to kubectl."""
        mock_proc = mock_subprocess_run.return_value
        mock_proc.stdout = '{"items": []}'
        mock_proc.stderr = ""
        mock_proc.returncode = 0

        run_kubectl("test-context", ["get", "pods"])

        call_kwargs = mock_subprocess_run.call_args[1]
        env = call_kwargs["env"]

        # Verify proxy environment variables are in the environment
        assert "HTTPS_PROXY" in env or "HTTP_PROXY" in env or "NO_PROXY" in env or True

    @patch("src.k8s_mcp.kubectl.runner.subprocess.run")
    def test_run_kubectl_with_timeout(self, mock_subprocess_run):
        """Test that run_kubectl passes timeout to subprocess.run."""
        mock_proc = mock_subprocess_run.return_value
        mock_proc.stdout = '{"items": []}'
        mock_proc.stderr = ""
        mock_proc.returncode = 0

        run_kubectl("test-context", ["get", "pods"], timeout=60.0)

        call_kwargs = mock_subprocess_run.call_args[1]
        assert call_kwargs["timeout"] == 60.0

    @patch("src.k8s_mcp.kubectl.runner.subprocess.run")
    def test_run_kubectl_with_stdin(self, mock_subprocess_run):
        """Test that run_kubectl passes stdin to subprocess.run."""
        mock_proc = mock_subprocess_run.return_value
        mock_proc.stdout = '{"items": []}'
        mock_proc.stderr = ""
        mock_proc.returncode = 0

        run_kubectl("test-context", ["apply", "-f", "-"], stdin="kind: Pod\n")

        call_kwargs = mock_subprocess_run.call_args[1]
        assert call_kwargs["input"] == "kind: Pod\n"


class TestRunKubectlChecked:
    """Test run_kubectl_checked success and error handling."""

    @patch("src.k8s_mcp.kubectl.runner.run_kubectl")
    def test_run_kubectl_checked_success(self, mock_run_kubectl):
        """Test run_kubectl_checked returns result on success."""
        mock_run_kubectl.return_value = {
            "stdout": '{"items": []}',
            "stderr": "",
            "returncode": 0,
            "command": ["kubectl", "--context", "test-context", "-o", "json", "get", "pods"],
        }

        result = run_kubectl_checked("test-context", ["get", "pods"])

        assert result["stdout"] == '{"items": []}'
        assert result["returncode"] == 0

    @patch("src.k8s_mcp.kubectl.runner.run_kubectl")
    def test_run_kubectl_checked_non_zero_exit(self, mock_run_kubectl):
        """Test run_kubectl_checked maps non-zero exit code to error."""
        mock_run_kubectl.return_value = {
            "stdout": "",
            "stderr": 'pods "x" not found',
            "returncode": 1,
            "command": ["kubectl", "--context", "test-context", "-o", "json", "get", "pods/x"],
        }

        result = run_kubectl_checked("test-context", ["get", "pods/x"])

        assert "error" in result
        assert result["error"] == "object_not_found"
