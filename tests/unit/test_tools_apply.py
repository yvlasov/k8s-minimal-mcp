"""Tests for tools/apply.py — handle_apply with jsonpath support."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.k8s_mcp.tools.apply import handle_apply
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


class TestHandleApply:
    @patch("src.k8s_mcp.tools.apply.resolve")
    @patch("src.k8s_mcp.tools.apply.run_kubectl_checked")
    def test_apply_default_json(self, mock_run, mock_resolve, deployment_meta):
        mock_resolve.return_value = deployment_meta
        mock_run.return_value = {"stdout": '{"kind": "Deployment", "metadata": {"name": "test"}}'}

        manifest = '{"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": "test"}}'
        result = handle_apply("test-context", manifest, namespace="default")

        assert result["success"] is True
        assert "data" in result

    @patch("src.k8s_mcp.tools.apply.resolve")
    @patch("src.k8s_mcp.tools.apply.run_kubectl_checked")
    def test_apply_with_dry_run(self, mock_run, mock_resolve, deployment_meta):
        mock_resolve.return_value = deployment_meta
        mock_run.return_value = {"stdout": '{"kind": "Deployment", "metadata": {"name": "test"}}'}

        manifest = '{"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": "test"}}'
        result = handle_apply("test-context", manifest, namespace="default", dry_run="client")

        assert result["success"] is True
        assert result["data"]["dry_run"] == "client"


class TestHandleApplyJsonpath:
    @patch("src.k8s_mcp.tools.apply.resolve")
    @patch("src.k8s_mcp.tools.apply.run_kubectl_checked")
    def test_jsonpath_template_auto_triggers(self, mock_run, mock_resolve, deployment_meta):
        mock_resolve.return_value = deployment_meta
        mock_run.return_value = {"stdout": "3"}

        manifest = '{"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": "test"}}'
        result = handle_apply("test-context", manifest, namespace="default",
                              jsonpath_template="{.status.readyReplicas}")

        assert result["success"] is True
        assert result["data"]["data"] == "3"
        assert result["data"]["jsonpath_template"] == "{.status.readyReplicas}"
        assert mock_run.call_args[1]["output_format"] == "jsonpath={.status.readyReplicas}"

    @patch("src.k8s_mcp.tools.apply.resolve")
    @patch("src.k8s_mcp.tools.apply.run_kubectl_checked")
    def test_jsonpath_explicit_output(self, mock_run, mock_resolve, deployment_meta):
        mock_resolve.return_value = deployment_meta
        mock_run.return_value = {"stdout": "nginx"}

        manifest = '{"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": "test"}}'
        result = handle_apply("test-context", manifest, namespace="default", output="jsonpath",
                              jsonpath_template="{.spec.template.spec.containers[0].name}")

        assert result["success"] is True
        assert result["data"]["data"] == "nginx"

    @patch("src.k8s_mcp.tools.apply.resolve")
    def test_jsonpath_output_without_template_fails(self, mock_resolve, deployment_meta):
        mock_resolve.return_value = deployment_meta

        manifest = '{"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": "test"}}'
        result = handle_apply("test-context", manifest, namespace="default", output="jsonpath")

        assert result["success"] is False
        assert result["error"] == "invalid_output"

    @patch("src.k8s_mcp.tools.apply.resolve")
    @patch("src.k8s_mcp.tools.apply.run_kubectl_checked")
    def test_jsonpath_preserves_dry_run(self, mock_run, mock_resolve, deployment_meta):
        mock_resolve.return_value = deployment_meta
        mock_run.return_value = {"stdout": "2"}

        manifest = '{"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": "test"}}'
        result = handle_apply("test-context", manifest, namespace="default", dry_run="server",
                              jsonpath_template="{.status.replicas}")

        assert result["success"] is True
        assert result["data"]["dry_run"] == "server"
        assert result["data"]["jsonpath_template"] == "{.status.replicas}"


class TestHandleApplyOutputFormat:
    @patch("src.k8s_mcp.tools.apply.resolve")
    @patch("src.k8s_mcp.tools.apply.run_kubectl_checked")
    def test_output_yaml(self, mock_run, mock_resolve, deployment_meta):
        mock_resolve.return_value = deployment_meta
        mock_run.return_value = {"stdout": '{"kind": "Deployment", "metadata": {"name": "test"}}'}

        manifest = '{"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": "test"}}'
        result = handle_apply("test-context", manifest, namespace="default", output="yaml")

        assert result["success"] is True
        assert "_yaml" in result["data"]["data"]
        assert isinstance(result["data"]["data"]["_yaml"], str)
        assert "kind: Deployment" in result["data"]["data"]["_yaml"]

    @patch("src.k8s_mcp.tools.apply.resolve")
    @patch("src.k8s_mcp.tools.apply.run_kubectl_checked")
    def test_output_json(self, mock_run, mock_resolve, deployment_meta):
        mock_resolve.return_value = deployment_meta
        mock_run.return_value = {"stdout": '{"kind": "Deployment", "metadata": {"name": "test"}}'}

        manifest = '{"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": "test"}}'
        result = handle_apply("test-context", manifest, namespace="default", output="json")

        assert result["success"] is True
        assert "data" in result["data"]
        assert result["data"]["data"]["kind"] == "Deployment"

    @patch("src.k8s_mcp.tools.apply.resolve")
    def test_output_wide_rejected(self, mock_resolve, deployment_meta):
        mock_resolve.return_value = deployment_meta

        manifest = '{"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": "test"}}'
        result = handle_apply("test-context", manifest, namespace="default", output="wide")

        assert result["success"] is False
        assert result["error"] == "invalid_output"

    @patch("src.k8s_mcp.tools.apply.resolve")
    def test_nested_brace_jsonpath_template_rejected(self, mock_resolve, deployment_meta):
        mock_resolve.return_value = deployment_meta

        manifest = '{"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": "test"}}'
        result = handle_apply("test-context", manifest, namespace="default",
                              jsonpath_template="{.items[*].{a,b}}")

        assert result["success"] is False
        assert result["error"] == "invalid_jsonpath_template"
        assert "Nested braces" in result.get("detail", "")

    @patch("src.k8s_mcp.tools.apply.resolve")
    @patch("src.k8s_mcp.tools.apply.run_kubectl_checked")
    def test_sibling_braces_jsonpath_template_allowed(self, mock_run, mock_resolve, deployment_meta):
        mock_resolve.return_value = deployment_meta
        mock_run.return_value = {"stdout": "ready"}

        manifest = '{"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": "test"}}'
        result = handle_apply("test-context", manifest, namespace="default",
                              jsonpath_template="{.status.readyReplicas}{.metadata.name}")

        assert result["success"] is True
        assert result["data"]["jsonpath_template"] == "{.status.readyReplicas}{.metadata.name}"
