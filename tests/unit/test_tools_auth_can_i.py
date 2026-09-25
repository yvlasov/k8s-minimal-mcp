"""Tests for tools/auth_can_i.py — handle_auth_can_i (FR13)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.k8s_mcp.tools.auth_can_i import handle_auth_can_i


class TestHandleAuthCanI:
    @patch("src.k8s_mcp.tools.auth_can_i.run_kubectl")
    def test_single_check_allowed(self, mock_run):
        mock_run.return_value = {
            "stdout": "allowed\n",
            "stderr": "",
            "returncode": 0,
            "command": ["kubectl", "--context", "test", "auth", "can-i", "get", "pods"],
        }

        result = handle_auth_can_i("test-context", verb="get", resource="pods")

        assert result["success"] is True
        assert result["data"]["allowed"] is True
        args = mock_run.call_args[0][1]
        assert args == ["auth", "can-i", "get", "pods"]

    @patch("src.k8s_mcp.tools.auth_can_i.run_kubectl")
    def test_single_check_denied(self, mock_run):
        mock_run.return_value = {
            "stdout": "",
            "stderr": "denied\n",
            "returncode": 1,
            "command": ["kubectl", "--context", "test", "auth", "can-i", "list", "secrets"],
        }

        result = handle_auth_can_i("test-context", verb="list", resource="secrets")

        assert result["success"] is True
        assert result["data"]["allowed"] is False

    @patch("src.k8s_mcp.tools.auth_can_i.run_kubectl")
    def test_single_check_with_namespace(self, mock_run):
        mock_run.return_value = {
            "stdout": "allowed\n",
            "stderr": "",
            "returncode": 0,
            "command": ["kubectl", "--context", "test", "-n", "kube-system", "auth", "can-i", "get", "pods"],
        }

        result = handle_auth_can_i("test-context", verb="get", resource="pods", namespace="kube-system")

        assert result["success"] is True
        assert result["data"]["allowed"] is True
        args = mock_run.call_args[0][1]
        assert "-n" in args
        assert "kube-system" in args

    @patch("src.k8s_mcp.tools.auth_can_i.run_kubectl")
    def test_single_check_with_resource_and_name(self, mock_run):
        mock_run.return_value = {
            "stdout": "allowed\n",
            "stderr": "",
            "returncode": 0,
            "command": ["kubectl", "--context", "test", "auth", "can-i", "get", "pods/my-pod"],
        }

        result = handle_auth_can_i("test-context", verb="get", resource="pods", name="my-pod")

        assert result["success"] is True
        args = mock_run.call_args[0][1]
        assert "pods/my-pod" in args

    @patch("src.k8s_mcp.tools.auth_can_i.run_kubectl")
    def test_single_check_with_as_user(self, mock_run):
        mock_run.return_value = {
            "stdout": "allowed\n",
            "stderr": "",
            "returncode": 0,
            "command": ["kubectl", "--context", "test", "--as", "alice@example.com", "auth", "can-i", "get", "pods"],
        }

        result = handle_auth_can_i("test-context", verb="get", resource="pods", as_user="alice@example.com")

        assert result["success"] is True
        args = mock_run.call_args[0][1]
        assert "--as" in args
        assert "alice@example.com" in args

    @patch("src.k8s_mcp.tools.auth_can_i.run_kubectl")
    def test_single_check_with_as_group(self, mock_run):
        mock_run.return_value = {
            "stdout": "allowed\n",
            "stderr": "",
            "returncode": 0,
            "command": ["kubectl", "--context", "test", "--as-group", "system:authenticated", "--as-group", "devs", "auth", "can-i", "get", "pods"],
        }

        result = handle_auth_can_i("test-context", verb="get", resource="pods", as_group=["system:authenticated", "devs"])

        assert result["success"] is True
        args = mock_run.call_args[0][1]
        group_indices = [i for i, a in enumerate(args) if a == "--as-group"]
        assert len(group_indices) == 2
        assert args[group_indices[0] + 1] == "system:authenticated"
        assert args[group_indices[1] + 1] == "devs"

    @patch("src.k8s_mcp.tools.auth_can_i.run_kubectl")
    def test_arg_order_as_before_groups(self, mock_run):
        """Verify --as comes before --as-group in the built args (order matters)."""
        mock_run.return_value = {
            "stdout": "allowed\n",
            "stderr": "",
            "returncode": 0,
            "command": ["kubectl", "--context", "test", "--as", "bob", "--as-group", "admins", "auth", "can-i", "get", "pods"],
        }

        result = handle_auth_can_i("test-context", verb="get", resource="pods", as_user="bob", as_group=["admins"])

        assert result["success"] is True
        args = mock_run.call_args[0][1]
        as_idx = args.index("--as")
        as_group_idx = args.index("--as-group")
        assert as_idx < as_group_idx

    @patch("src.k8s_mcp.tools.auth_can_i.run_kubectl")
    def test_list_all_mode(self, mock_run):
        mock_run.return_value = {
            "stdout": "Resources Granted\n--------------- ---------\npods            [get, list, watch]\nsecrets         [get]\n",
            "stderr": "",
            "returncode": 0,
            "command": ["kubectl", "--context", "test", "auth", "can-i", "--list"],
        }

        result = handle_auth_can_i("test-context", list_all=True)

        assert result["success"] is True
        perms = result["data"]["permissions"]
        assert "pods" in perms
        assert perms["pods"] == ["get", "list", "watch"]
        assert perms["secrets"] == ["get"]

    @patch("src.k8s_mcp.tools.auth_can_i.run_kubectl")
    def test_list_all_empty(self, mock_run):
        mock_run.return_value = {
            "stdout": "Resources Granted\n--------------- ---------\n",
            "stderr": "",
            "returncode": 0,
            "command": ["kubectl", "--context", "test", "auth", "can-i", "--list"],
        }

        result = handle_auth_can_i("test-context", list_all=True)

        assert result["success"] is True
        assert result["data"]["permissions"] == {}

    @patch("src.k8s_mcp.tools.auth_can_i.run_kubectl")
    def test_non_zero_exit_code_kubectl_failure(self, mock_run):
        mock_run.return_value = {
            "stdout": "",
            "stderr": "error: unknown command",
            "returncode": 2,
            "command": ["kubectl", "--context", "test", "auth", "can-i", "get", "pods"],
        }

        result = handle_auth_can_i("test-context", verb="get", resource="pods")

        assert result["success"] is False
        assert result["error"] == "kubectl_failure"
        assert "error: unknown command" in result["stderr"]
        assert result.get("exit_code") == 2

    @patch("src.k8s_mcp.tools.auth_can_i.run_kubectl")
    def test_list_all_non_zero_exit_code(self, mock_run):
        mock_run.return_value = {
            "stdout": "",
            "stderr": "auth can-i --list failed",
            "returncode": 3,
            "command": ["kubectl", "--context", "test", "auth", "can-i", "--list"],
        }

        result = handle_auth_can_i("test-context", list_all=True)

        assert result["success"] is False
        assert result["error"] == "kubectl_failure"
        assert "auth can-i --list failed" in result["stderr"]

    @patch("src.k8s_mcp.tools.auth_can_i.run_kubectl")
    def test_kubectl_error_passthrough(self, mock_run):
        mock_run.return_value = {"error": "kubectl binary not found in PATH"}

        result = handle_auth_can_i("test-context", verb="get", resource="pods")

        assert result["success"] is False
        assert result["error"] == "kubectl_failure"

    @patch("src.k8s_mcp.tools.auth_can_i.run_kubectl")
    def test_command_included_in_response(self, mock_run):
        mock_run.return_value = {
            "stdout": "allowed\n",
            "stderr": "",
            "returncode": 0,
            "command": ["kubectl", "--context", "test", "auth", "can-i", "get", "pods"],
        }

        result = handle_auth_can_i("test-context", verb="get", resource="pods")

        assert result["success"] is True
        assert result["data"]["command"] == ["kubectl", "--context", "test", "auth", "can-i", "get", "pods"]

    @patch("src.k8s_mcp.tools.auth_can_i.run_kubectl")
    def test_list_all_command_included(self, mock_run):
        mock_run.return_value = {
            "stdout": "Resources Granted\n--------------- ---------\npods            [get]\n",
            "stderr": "",
            "returncode": 0,
            "command": ["kubectl", "--context", "test", "auth", "can-i", "--list"],
        }

        result = handle_auth_can_i("test-context", list_all=True)

        assert result["success"] is True
        assert result["data"]["command"] == ["kubectl", "--context", "test", "auth", "can-i", "--list"]
