"""Tests for tools/patch.py — handle_patch with jsonpath support."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.k8s_mcp.tools.patch import handle_patch
from src.k8s_mcp.resolution.models import ResourceMeta


@pytest.fixture
def deployment_meta():
    return ResourceMeta(
        canonical="deployments",
        shortnames=["deploy"],
        kind="Deployment",
        group="apps",
        version="v1",
        namespaced=True,
        verbs=["get", "apply", "patch", "delete", "list"],
    )


class TestHandlePatch:
    @patch("src.k8s_mcp.tools.patch.resolve")
    @patch("src.k8s_mcp.tools.patch.run_kubectl_checked")
    def test_patch_default_json(self, mock_run, mock_resolve, deployment_meta):
        mock_resolve.return_value = deployment_meta
        mock_run.return_value = {"stdout": '{"kind": "Deployment", "metadata": {"name": "test"}}'}

        result = handle_patch("test-context", "deployments", "my-deploy", '{"spec": {"replicas": 3}}',
                              namespace="default")

        assert result["success"] is True
        assert "data" in result

    @patch("src.k8s_mcp.tools.patch.resolve")
    @patch("src.k8s_mcp.tools.patch.run_kubectl_checked")
    def test_patch_with_dry_run(self, mock_run, mock_resolve, deployment_meta):
        mock_resolve.return_value = deployment_meta
        mock_run.return_value = {"stdout": '{"kind": "Deployment", "metadata": {"name": "test"}}'}

        result = handle_patch("test-context", "deployments", "my-deploy", '{"spec": {"replicas": 3}}',
                              namespace="default", dry_run="client")

        assert result["success"] is True
        assert result["data"]["dry_run"] == "client"


class TestHandlePatchJsonpath:
    @patch("src.k8s_mcp.tools.patch.resolve")
    @patch("src.k8s_mcp.tools.patch.run_kubectl_checked")
    def test_jsonpath_template_auto_triggers(self, mock_run, mock_resolve, deployment_meta):
        mock_resolve.return_value = deployment_meta
        mock_run.return_value = {"stdout": "3"}

        result = handle_patch("test-context", "deployments", "my-deploy", '{"spec": {"replicas": 3}}',
                              namespace="default",
                              jsonpath_template="{.status.readyReplicas}")

        assert result["success"] is True
        assert result["data"]["data"] == "3"
        assert result["data"]["jsonpath_template"] == "{.status.readyReplicas}"
        assert mock_run.call_args[1]["output_format"] == "jsonpath={.status.readyReplicas}"

    @patch("src.k8s_mcp.tools.patch.resolve")
    @patch("src.k8s_mcp.tools.patch.run_kubectl_checked")
    def test_jsonpath_explicit_output(self, mock_run, mock_resolve, deployment_meta):
        mock_resolve.return_value = deployment_meta
        mock_run.return_value = {"stdout": "nginx"}

        result = handle_patch("test-context", "deployments", "my-deploy", '{"spec": {"replicas": 3}}',
                              namespace="default", output="jsonpath",
                              jsonpath_template="{.spec.template.spec.containers[0].name}")

        assert result["success"] is True
        assert result["data"]["data"] == "nginx"

    @patch("src.k8s_mcp.tools.patch.resolve")
    def test_jsonpath_output_without_template_fails(self, mock_resolve, deployment_meta):
        mock_resolve.return_value = deployment_meta

        result = handle_patch("test-context", "deployments", "my-deploy", '{"spec": {"replicas": 3}}',
                              namespace="default", output="jsonpath")

        assert result["success"] is False
        assert result["error"] == "invalid_output"

    @patch("src.k8s_mcp.tools.patch.resolve")
    @patch("src.k8s_mcp.tools.patch.run_kubectl_checked")
    def test_jsonpath_preserves_dry_run(self, mock_run, mock_resolve, deployment_meta):
        mock_resolve.return_value = deployment_meta
        mock_run.return_value = {"stdout": "2"}

        result = handle_patch("test-context", "deployments", "my-deploy", '{"spec": {"replicas": 3}}',
                              namespace="default", dry_run="server",
                              jsonpath_template="{.status.replicas}")

        assert result["success"] is True
        assert result["data"]["dry_run"] == "server"
        assert result["data"]["jsonpath_template"] == "{.status.replicas}"


class TestHandlePatchOutputFormat:
    @patch("src.k8s_mcp.tools.patch.resolve")
    @patch("src.k8s_mcp.tools.patch.run_kubectl_checked")
    def test_output_yaml(self, mock_run, mock_resolve, deployment_meta):
        mock_resolve.return_value = deployment_meta
        mock_run.return_value = {"stdout": '{"kind": "Deployment", "metadata": {"name": "test"}}'}

        result = handle_patch("test-context", "deployments", "my-deploy", '{"spec": {"replicas": 3}}',
                              namespace="default", output="yaml")

        assert result["success"] is True
        assert "_yaml" in result["data"]["data"]
        assert isinstance(result["data"]["data"]["_yaml"], str)
        assert "kind: Deployment" in result["data"]["data"]["_yaml"]

    @patch("src.k8s_mcp.tools.patch.resolve")
    @patch("src.k8s_mcp.tools.patch.run_kubectl_checked")
    def test_output_json(self, mock_run, mock_resolve, deployment_meta):
        mock_resolve.return_value = deployment_meta
        mock_run.return_value = {"stdout": '{"kind": "Deployment", "metadata": {"name": "test"}}'}

        result = handle_patch("test-context", "deployments", "my-deploy", '{"spec": {"replicas": 3}}',
                              namespace="default", output="json")

        assert result["success"] is True
        assert "data" in result["data"]
        assert result["data"]["data"]["kind"] == "Deployment"

    @patch("src.k8s_mcp.tools.patch.resolve")
    def test_output_wide_rejected(self, mock_resolve, deployment_meta):
        mock_resolve.return_value = deployment_meta

        result = handle_patch("test-context", "deployments", "my-deploy", '{"spec": {"replicas": 3}}',
                              namespace="default", output="wide")

        assert result["success"] is False
        assert result["error"] == "invalid_output"

    @patch("src.k8s_mcp.tools.patch.resolve")
    def test_nested_brace_jsonpath_template_rejected(self, mock_resolve, deployment_meta):
        mock_resolve.return_value = deployment_meta

        result = handle_patch("test-context", "deployments", "my-deploy", '{"spec": {"replicas": 3}}',
                              namespace="default", jsonpath_template="{.items[*].{a,b}}")

        assert result["success"] is False
        assert result["error"] == "invalid_jsonpath_template"
        assert "Nested braces" in result.get("detail", "")

    @patch("src.k8s_mcp.tools.patch.resolve")
    @patch("src.k8s_mcp.tools.patch.run_kubectl_checked")
    def test_sibling_braces_jsonpath_template_allowed(self, mock_run, mock_resolve, deployment_meta):
        mock_resolve.return_value = deployment_meta
        mock_run.return_value = {"stdout": "ready"}

        result = handle_patch("test-context", "deployments", "my-deploy", '{"spec": {"replicas": 3}}',
                              namespace="default", jsonpath_template="{.status.readyReplicas}{.metadata.name}")

        assert result["success"] is True
        assert result["data"]["jsonpath_template"] == "{.status.readyReplicas}{.metadata.name}"


class TestHandlePatchFullyQualifiedResource:
    """Issue 38: group-qualified resource names must reach kubectl."""

    @patch("src.k8s_mcp.tools.patch.resolve")
    @patch("src.k8s_mcp.tools.patch.run_kubectl_checked")
    def test_groupful_resource_uses_fully_qualified_name(self, mock_run, mock_resolve):
        node_metrics_meta = ResourceMeta(
            canonical="nodes",
            shortnames=[],
            kind="NodeMetrics",
            group="metrics.k8s.io",
            version="v1beta1",
            namespaced=False,
            verbs=["get", "patch", "list"],
        )
        mock_resolve.return_value = node_metrics_meta
        mock_run.return_value = {"stdout": '{"kind": "NodeMetrics", "metadata": {"name": "my-node"}}'}

        result = handle_patch("test-context", "nodes.metrics.k8s.io", "my-node", '{"usage": {"cpu": "100m"}}')

        assert result["success"] is True
        args = mock_run.call_args[0][1]
        assert args[1] == "nodes.metrics.k8s.io"

    @patch("src.k8s_mcp.tools.patch.resolve")
    @patch("src.k8s_mcp.tools.patch.run_kubectl_checked")
    def test_groupful_resource_uses_fully_qualified_name_with_namespace(self, mock_run, mock_resolve, deployment_meta):
        mock_resolve.return_value = deployment_meta
        mock_run.return_value = {"stdout": '{"kind": "Deployment", "metadata": {"name": "test"}}'}

        result = handle_patch("test-context", "deployments", "my-deploy", '{"spec": {"replicas": 3}}',
                              namespace="default")

        assert result["success"] is True
        args = mock_run.call_args[0][1]
        assert args[1] == "deployments.apps"
