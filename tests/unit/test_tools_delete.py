"""Tests for tools/delete.py — handle_delete."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.k8s_mcp.tools.delete import handle_delete
from src.k8s_mcp.resolution.models import ResourceMeta


@pytest.fixture
def deploy_meta():
    return ResourceMeta(
        canonical="deployments",
        shortnames=["deploy"],
        kind="Deployment",
        group="apps",
        version="v1",
        namespaced=True,
        verbs=["get", "apply", "patch", "delete", "list"],
    )


class TestHandleDelete:
    @patch("src.k8s_mcp.tools.delete.resolve")
    @patch("src.k8s_mcp.tools.delete.run_kubectl_checked")
    def test_delete_with_name(self, mock_run, mock_resolve, deploy_meta):
        mock_resolve.return_value = deploy_meta
        mock_run.return_value = {"stdout": '{"kind": "DeleteOptions", "metadata": {}}'}

        result = handle_delete("test-context", "deployments", name="my-deploy", namespace="default")

        assert result["success"] is True
        args = mock_run.call_args[0][1]
        assert "my-deploy" in args
        assert "-l" not in args
        assert "-n" in args
        assert "default" in args

    @patch("src.k8s_mcp.tools.delete.resolve")
    @patch("src.k8s_mcp.tools.delete.run_kubectl_checked")
    def test_delete_output_format_none(self, mock_run, mock_resolve, deploy_meta):
        mock_resolve.return_value = deploy_meta
        mock_run.return_value = {"stdout": "deployment.apps/my-deploy deleted"}

        handle_delete("test-context", "deployments", name="my-deploy", namespace="default")

        assert mock_run.call_args[1]["output_format"] is None

    @patch("src.k8s_mcp.tools.delete.resolve")
    @patch("src.k8s_mcp.tools.delete.run_kubectl_checked")
    def test_delete_with_label_selector(self, mock_run, mock_resolve, deploy_meta):
        mock_resolve.return_value = deploy_meta
        mock_run.return_value = {"stdout": '{"kind": "DeleteOptions", "metadata": {}}'}

        result = handle_delete("test-context", "deployments", label_selector="app=nginx", namespace="default")

        assert result["success"] is True
        args = mock_run.call_args[0][1]
        assert "-l" in args
        assert "app=nginx" in args

    @patch("src.k8s_mcp.tools.delete.resolve")
    @patch("src.k8s_mcp.tools.delete.run_kubectl_checked")
    def test_delete_name_wins_over_label_selector(self, mock_run, mock_resolve, deploy_meta):
        mock_resolve.return_value = deploy_meta
        mock_run.return_value = {"stdout": '{"kind": "DeleteOptions", "metadata": {}}'}

        result = handle_delete("test-context", "deployments", name="my-deploy", label_selector="app=nginx", namespace="default")

        args = mock_run.call_args[0][1]
        assert args.count("-l") == 0  # name takes precedence, no -l flag

    @patch("src.k8s_mcp.tools.delete.resolve")
    @patch("src.k8s_mcp.tools.delete.run_kubectl_checked")
    def test_delete_dry_run_client(self, mock_run, mock_resolve, deploy_meta):
        mock_resolve.return_value = deploy_meta
        mock_run.return_value = {"stdout": '{"kind": "DeleteOptions", "metadata": {}}'}

        result = handle_delete("test-context", "deployments", name="my-deploy", dry_run="client", namespace="default")

        assert result["success"] is True
        assert result["data"]["dry_run"] == "client"
        args = mock_run.call_args[0][1]
        assert "--dry-run" in args
        assert "client" in args

    @patch("src.k8s_mcp.tools.delete.resolve")
    @patch("src.k8s_mcp.tools.delete.run_kubectl_checked")
    def test_delete_dry_run_server(self, mock_run, mock_resolve, deploy_meta):
        mock_resolve.return_value = deploy_meta
        mock_run.return_value = {"stdout": '{"kind": "DeleteOptions", "metadata": {}}'}

        result = handle_delete("test-context", "deployments", name="my-deploy", dry_run="server", namespace="default")

        assert result["data"]["dry_run"] == "server"

    @patch("src.k8s_mcp.tools.delete.resolve")
    @patch("src.k8s_mcp.tools.delete.run_kubectl_checked")
    def test_delete_dry_run_none_no_flag(self, mock_run, mock_resolve, deploy_meta):
        mock_resolve.return_value = deploy_meta
        mock_run.return_value = {"stdout": '{"kind": "DeleteOptions", "metadata": {}}'}

        result = handle_delete("test-context", "deployments", name="my-deploy", dry_run="none", namespace="default")

        assert result["data"]["dry_run"] is False
        args = mock_run.call_args[0][1]
        assert "--dry-run" not in args

    @patch("src.k8s_mcp.tools.delete.resolve")
    @patch("src.k8s_mcp.tools.delete.run_kubectl_checked")
    def test_delete_json_response_pruned(self, mock_run, mock_resolve, deploy_meta):
        mock_resolve.return_value = deploy_meta
        mock_run.return_value = {"stdout": '{"kind": "Deployment", "metadata": {"name": "test", "uid": "123", "managedFields": []}}'}

        result = handle_delete("test-context", "deployments", name="my-deploy", namespace="default")

        assert result["success"] is True
        assert "data" in result
        assert "managedFields" not in result["data"]

    @patch("src.k8s_mcp.tools.delete.resolve")
    @patch("src.k8s_mcp.tools.delete.run_kubectl_checked")
    def test_delete_non_json_fallback(self, mock_run, mock_resolve, deploy_meta):
        mock_resolve.return_value = deploy_meta
        mock_run.return_value = {"stdout": "deployment.apps/my-deploy deleted"}

        result = handle_delete("test-context", "deployments", name="my-deploy", namespace="default")

        assert result["success"] is True
        assert "data" in result["data"]
        assert "deleted" in result["data"]["data"]["message"]

    @patch("src.k8s_mcp.tools.delete.resolve")
    def test_delete_resolve_error(self, mock_resolve, deploy_meta):
        mock_resolve.return_value = {"error": "unknown_resource", "detail": "deployments not found"}

        result = handle_delete("test-context", "deployments", name="my-deploy")

        assert result["success"] is False
        assert result["error"] == "unknown_resource"

    @patch("src.k8s_mcp.tools.delete.resolve")
    @patch("src.k8s_mcp.tools.delete.run_kubectl_checked")
    def test_delete_kubectl_error(self, mock_run, mock_resolve, deploy_meta):
        mock_resolve.return_value = deploy_meta
        mock_run.return_value = {"error": "access_denied", "detail": "forbidden"}

        result = handle_delete("test-context", "deployments", name="my-deploy", namespace="default")

        assert result["success"] is False
        assert result["error"] == "access_denied"


class TestHandleDeleteFullyQualifiedResource:
    """Issue 38: group-qualified resource names must reach kubectl."""

    @patch("src.k8s_mcp.tools.delete.resolve")
    @patch("src.k8s_mcp.tools.delete.run_kubectl_checked")
    def test_groupful_resource_uses_fully_qualified_name(self, mock_run, mock_resolve):
        node_metrics_meta = ResourceMeta(
            canonical="nodes",
            shortnames=[],
            kind="NodeMetrics",
            group="metrics.k8s.io",
            version="v1beta1",
            namespaced=False,
            verbs=["get", "list", "delete"],
        )
        mock_resolve.return_value = node_metrics_meta
        mock_run.return_value = {"stdout": "nodes.metrics.k8s.io deleted"}

        result = handle_delete("test-context", "nodes.metrics.k8s.io", name="my-node")

        assert result["success"] is True
        args = mock_run.call_args[0][1]
        assert args[1] == "nodes.metrics.k8s.io"

    @patch("src.k8s_mcp.tools.delete.resolve")
    @patch("src.k8s_mcp.tools.delete.run_kubectl_checked")
    def test_groupful_resource_uses_fully_qualified_name_with_namespace(self, mock_run, mock_resolve):
        deploy_meta = ResourceMeta(
            canonical="deployments",
            shortnames=["deploy"],
            kind="Deployment",
            group="apps",
            version="v1",
            namespaced=True,
            verbs=["get", "apply", "patch", "delete", "list"],
        )
        mock_resolve.return_value = deploy_meta
        mock_run.return_value = {"stdout": "deployment.apps/my-deploy deleted"}

        result = handle_delete("test-context", "deployments", name="my-deploy", namespace="default")

        assert result["success"] is True
        args = mock_run.call_args[0][1]
        assert args[1] == "deployments.apps"
