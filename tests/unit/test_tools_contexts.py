"""Tests for tools/contexts.py — handle_list_contexts."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.k8s_mcp.tools.contexts import handle_list_contexts


class TestHandleListContexts:
    @patch("src.k8s_mcp.tools.contexts.list_kubeconfig_contexts")
    def test_list_contexts_happy_path(self, mock_list, tmp_path):
        mock_list.return_value = ["context1", "context2", "context3"]

        result = handle_list_contexts("test-context")

        assert result["success"] is True
        assert result["data"]["contexts"] == ["context1", "context2", "context3"]
        assert result["data"]["count"] == 3

    @patch("src.k8s_mcp.tools.contexts.list_kubeconfig_contexts")
    def test_list_contexts_kubeconfig_paths_normalized(self, mock_list, tmp_path):
        mock_list.return_value = ["context1"]

        handle_list_contexts("test-context", kubeconfig_paths=None)

        mock_list.assert_called_once_with([])

    @patch("src.k8s_mcp.tools.contexts.list_kubeconfig_contexts")
    def test_list_contexts_error_surfaced(self, mock_list, tmp_path):
        mock_list.return_value = {"error": "kubeconfig_error", "detail": "invalid kubeconfig"}

        result = handle_list_contexts("test-context")

        assert result["success"] is False
        assert result["error"] == "kubeconfig_error"
        assert "detail" in result

    @patch("src.k8s_mcp.tools.contexts.list_kubeconfig_contexts")
    def test_list_contexts_empty_result(self, mock_list, tmp_path):
        mock_list.return_value = []

        result = handle_list_contexts("test-context")

        assert result["success"] is True
        assert result["data"]["contexts"] == []
        assert result["data"]["count"] == 0

    @patch("src.k8s_mcp.tools.contexts.list_kubeconfig_contexts")
    def test_list_contexts_custom_kubeconfig_paths(self, mock_list, tmp_path):
        mock_list.return_value = ["context1"]

        handle_list_contexts("test-context", kubeconfig_paths=["/path/to/kubeconfig"])

        mock_list.assert_called_once_with(["/path/to/kubeconfig"])
