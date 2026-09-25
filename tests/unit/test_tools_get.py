"""Tests for tools/get.py — handle_get with all_namespaces."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.k8s_mcp.tools.get import handle_get
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


class TestHandleGet:
    @patch("src.k8s_mcp.tools.get.resolve")
    @patch("src.k8s_mcp.tools.get.run_kubectl_checked")
    def test_all_namespaces_true_reaches_kubectl(self, mock_run, mock_resolve, pod_meta):
        mock_resolve.return_value = pod_meta
        mock_run.return_value = {"stdout": '{"items": []}'}

        result = handle_get("test-context", "pods", all_namespaces=True)

        assert result["success"] is True
        mock_run.assert_called_once()
        args = mock_run.call_args[0][1]
        assert "--all-namespaces" in args

    @patch("src.k8s_mcp.tools.get.resolve")
    @patch("src.k8s_mcp.tools.get.run_kubectl_checked")
    def test_all_namespaces_false_with_namespace(self, mock_run, mock_resolve, pod_meta):
        mock_resolve.return_value = pod_meta
        mock_run.return_value = {"stdout": '{"items": []}'}

        result = handle_get("test-context", "pods", namespace="default", all_namespaces=False)

        assert result["success"] is True
        args = mock_run.call_args[0][1]
        assert "-n" in args
        assert "default" in args
        assert "--all-namespaces" not in args

    @patch("src.k8s_mcp.tools.get.resolve")
    def test_all_namespaces_false_without_namespace_returns_error(self, mock_resolve, pod_meta):
        mock_resolve.return_value = pod_meta

        result = handle_get("test-context", "pods", namespace=None, all_namespaces=False)

        assert result["success"] is False
        assert result["error"] == "namespace_invalid"


class TestHandleGetJsonpath:
    @patch("src.k8s_mcp.tools.get.resolve")
    @patch("src.k8s_mcp.tools.get.run_kubectl_checked")
    def test_jsonpath_template_auto_triggers(self, mock_run, mock_resolve, pod_meta):
        mock_resolve.return_value = pod_meta
        mock_run.return_value = {"stdout": "10.0.0.1"}

        result = handle_get("test-context", "pods", name="my-pod", namespace="default",
                            jsonpath_template="{.status.podIP}")

        assert result["success"] is True
        assert result["data"]["data"] == "10.0.0.1"
        assert result["data"]["jsonpath_template"] == "{.status.podIP}"
        assert mock_run.call_args[1]["output_format"] == "jsonpath={.status.podIP}"

    @patch("src.k8s_mcp.tools.get.resolve")
    @patch("src.k8s_mcp.tools.get.run_kubectl_checked")
    def test_jsonpath_explicit_output(self, mock_run, mock_resolve, pod_meta):
        mock_resolve.return_value = pod_meta
        mock_run.return_value = {"stdout": "nginx"}

        result = handle_get("test-context", "pods", name="my-pod", namespace="default",
                            output="jsonpath", jsonpath_template="{.spec.containers[0].name}")

        assert result["success"] is True
        assert result["data"]["data"] == "nginx"

    @patch("src.k8s_mcp.tools.get.resolve")
    def test_jsonpath_output_without_template_fails(self, mock_resolve, pod_meta):
        mock_resolve.return_value = pod_meta

        result = handle_get("test-context", "pods", name="my-pod", output="jsonpath")

        assert result["success"] is False
        assert result["error"] == "invalid_output"

    @patch("src.k8s_mcp.tools.get.resolve")
    @patch("src.k8s_mcp.tools.get.run_kubectl_checked")
    def test_jsonpath_stdout_not_pruned(self, mock_run, mock_resolve, pod_meta):
        mock_resolve.return_value = pod_meta
        mock_run.return_value = {"stdout": '{"uid": "123", "metadata": {"managedFields": []}}'}

        result = handle_get("test-context", "pods", name="my-pod", namespace="default",
                            jsonpath_template="{.metadata}")

        assert result["success"] is True
        assert result["data"]["data"] == '{"uid": "123", "metadata": {"managedFields": []}}'


class TestHandleGetAnnotationSelector:
    @patch("src.k8s_mcp.tools.get.resolve")
    @patch("src.k8s_mcp.tools.get.run_kubectl_checked")
    def test_annotation_selector_equality(self, mock_run, mock_resolve, pod_meta):
        mock_resolve.return_value = pod_meta
        mock_run.return_value = {"stdout": '{"items": [{"metadata": {"name": "nginx-pod", "annotations": {"app": "nginx"}}}, {"metadata": {"name": "redis-pod", "annotations": {"app": "redis"}}}]}'}

        result = handle_get("test-context", "pods", namespace="default",
                            annotation_selector="app=nginx")

        assert result["success"] is True
        assert result["data"]["_filtered"]["matched"] == 1
        assert result["data"]["_filtered"]["total"] == 2
        assert len(result["data"]["items"]) == 1
        assert result["data"]["items"][0]["name"] == "nginx-pod"

    @patch("src.k8s_mcp.tools.get.resolve")
    @patch("src.k8s_mcp.tools.get.run_kubectl_checked")
    def test_annotation_selector_inequality(self, mock_run, mock_resolve, pod_meta):
        mock_resolve.return_value = pod_meta
        mock_run.return_value = {"stdout": '{"items": [{"metadata": {"name": "nginx-pod", "annotations": {"app": "nginx"}}}, {"metadata": {"name": "redis-pod", "annotations": {"app": "redis"}}}]}'}

        result = handle_get("test-context", "pods", namespace="default",
                            annotation_selector="app!=redis")

        assert result["success"] is True
        assert result["data"]["_filtered"]["matched"] == 1
        assert len(result["data"]["items"]) == 1
        assert result["data"]["items"][0]["name"] == "nginx-pod"

    @patch("src.k8s_mcp.tools.get.resolve")
    @patch("src.k8s_mcp.tools.get.run_kubectl_checked")
    def test_annotation_selector_existence(self, mock_run, mock_resolve, pod_meta):
        mock_resolve.return_value = pod_meta
        mock_run.return_value = {"stdout": '{"items": [{"metadata": {"annotations": {"app": "nginx"}}}, {"metadata": {}}]}'}

        result = handle_get("test-context", "pods", namespace="default",
                            annotation_selector="app")

        assert result["success"] is True
        assert result["data"]["_filtered"]["matched"] == 1
        assert len(result["data"]["items"]) == 1

    @patch("src.k8s_mcp.tools.get.resolve")
    @patch("src.k8s_mcp.tools.get.run_kubectl_checked")
    def test_annotation_selector_and_semantics(self, mock_run, mock_resolve, pod_meta):
        mock_resolve.return_value = pod_meta
        mock_run.return_value = {"stdout": '{"items": [{"metadata": {"name": "nginx-prod", "annotations": {"app": "nginx", "env": "prod"}}}, {"metadata": {"name": "nginx-dev", "annotations": {"app": "nginx", "env": "dev"}}}, {"metadata": {"name": "redis-prod", "annotations": {"app": "redis", "env": "prod"}}}]}'}

        result = handle_get("test-context", "pods", namespace="default",
                            annotation_selector="app=nginx,env=prod")

        assert result["success"] is True
        assert result["data"]["_filtered"]["matched"] == 1
        assert result["data"]["_filtered"]["total"] == 3
        assert result["data"]["items"][0]["name"] == "nginx-prod"

    @patch("src.k8s_mcp.tools.get.resolve")
    def test_annotation_selector_malformed_syntax_fails(self, mock_resolve, pod_meta):
        mock_resolve.return_value = pod_meta

        result = handle_get("test-context", "pods", namespace="default",
                            annotation_selector="invalid syntax")

        assert result["success"] is False
        assert result["error"] == "invalid_selector"

    @patch("src.k8s_mcp.tools.get.resolve")
    def test_annotation_selector_empty_value_fails(self, mock_resolve, pod_meta):
        mock_resolve.return_value = pod_meta

        result = handle_get("test-context", "pods", namespace="default",
                            annotation_selector="app=")

        assert result["success"] is False
        assert result["error"] == "invalid_selector"

    @patch("src.k8s_mcp.tools.get.resolve")
    @patch("src.k8s_mcp.tools.get.run_kubectl_checked")
    def test_annotation_selector_forces_full_json_fetch(self, mock_run, mock_resolve, pod_meta):
        mock_resolve.return_value = pod_meta
        mock_run.return_value = {"stdout": '{"items": []}'}

        handle_get("test-context", "pods", namespace="default",
                   output="name", annotation_selector="app=nginx")

        assert mock_run.call_args[1].get("output_format") is None

    @patch("src.k8s_mcp.tools.get.resolve")
    def test_annotation_selector_rejects_jsonpath_template(self, mock_resolve, pod_meta):
        mock_resolve.return_value = pod_meta

        result = handle_get("test-context", "pods", namespace="default",
                            annotation_selector="app=nginx", jsonpath_template="{.metadata.name}")

        assert result["success"] is False
        assert result["error"] == "invalid_selector"
        assert "cannot combine" in result.get("detail", "")

    @patch("src.k8s_mcp.tools.get.resolve")
    @patch("src.k8s_mcp.tools.get.run_kubectl_checked")
    def test_annotation_selector_rejects_output_wide(self, mock_run, mock_resolve, pod_meta):
        mock_resolve.return_value = pod_meta

        result = handle_get("test-context", "pods", namespace="default",
                            annotation_selector="app=nginx", output="wide")

        assert result["success"] is False
        assert result["error"] == "invalid_selector"
        assert "cannot combine" in result.get("detail", "")
        mock_run.assert_not_called()

    @patch("src.k8s_mcp.tools.get.resolve")
    @patch("src.k8s_mcp.tools.get.run_kubectl_checked")
    def test_annotation_selector_no_matches(self, mock_run, mock_resolve, pod_meta):
        mock_resolve.return_value = pod_meta
        mock_run.return_value = {"stdout": '{"items": [{"metadata": {"annotations": {"app": "nginx"}}}]}'}

        result = handle_get("test-context", "pods", namespace="default",
                            annotation_selector="app=redis")

        assert result["success"] is True
        assert result["data"]["_filtered"]["matched"] == 0
        assert result["data"]["_filtered"]["total"] == 1
        assert len(result["data"]["items"]) == 0

    @patch("src.k8s_mcp.tools.get.resolve")
    @patch("src.k8s_mcp.tools.get.run_kubectl_checked")
    def test_annotation_selector_single_resource_match(self, mock_run, mock_resolve, pod_meta):
        mock_resolve.return_value = pod_meta
        mock_run.return_value = {"stdout": '{"kind": "Pod", "metadata": {"name": "mypod", "annotations": {"app": "nginx"}}}'}

        result = handle_get("test-context", "pods", name="mypod", namespace="default",
                            annotation_selector="app=nginx")

        assert result["success"] is True
        assert result["data"]["_filtered"]["matched"] == 1
        assert result["data"]["_filtered"]["total"] == 1
        assert result["data"]["items"][0]["name"] == "mypod"

    @patch("src.k8s_mcp.tools.get.resolve")
    @patch("src.k8s_mcp.tools.get.run_kubectl_checked")
    def test_annotation_selector_single_resource_no_match(self, mock_run, mock_resolve, pod_meta):
        mock_resolve.return_value = pod_meta
        mock_run.return_value = {"stdout": '{"kind": "Pod", "metadata": {"name": "mypod", "annotations": {"app": "nginx"}}}'}

        result = handle_get("test-context", "pods", name="mypod", namespace="default",
                            annotation_selector="app=redis")

        assert result["success"] is True
        assert result["data"]["_filtered"]["matched"] == 0
        assert result["data"]["_filtered"]["total"] == 1
        assert len(result["data"]["items"]) == 0


class TestHandleGetWide:
    @patch("src.k8s_mcp.tools.get.resolve")
    @patch("src.k8s_mcp.tools.get.run_kubectl_checked")
    def test_output_wide_uses_wide_format(self, mock_run, mock_resolve, pod_meta):
        mock_resolve.return_value = pod_meta
        mock_run.return_value = {"stdout": "NAME       READY   STATUS    RESTARTS   AGE\nmypod      1/1     Running   0          10d"}

        result = handle_get("test-context", "pods", name="mypod", namespace="default",
                            output="wide")

        assert result["success"] is True
        assert result["data"]["output"] == "NAME       READY   STATUS    RESTARTS   AGE\nmypod      1/1     Running   0          10d"
        assert mock_run.call_args[1]["output_format"] == "wide"

    @patch("src.k8s_mcp.tools.get.resolve")
    @patch("src.k8s_mcp.tools.get.run_kubectl_checked")
    def test_output_wide_with_selectors(self, mock_run, mock_resolve, pod_meta):
        mock_resolve.return_value = pod_meta
        mock_run.return_value = {"stdout": "NAME       READY   STATUS    RESTARTS   AGE\nmypod      1/1     Running   0          10d"}

        handle_get("test-context", "pods", namespace="default",
                   output="wide", label_selector="app=nginx", field_selector="status.phase=Running")

        args = mock_run.call_args[0][1]
        assert "-l" in args
        assert "--field-selector" in args
        assert mock_run.call_args[1]["output_format"] == "wide"

    @patch("src.k8s_mcp.tools.get.resolve")
    @patch("src.k8s_mcp.tools.get.run_kubectl_checked")
    def test_output_wide_not_pruned(self, mock_run, mock_resolve, pod_meta):
        mock_resolve.return_value = pod_meta
        mock_run.return_value = {"stdout": "NAME       READY   STATUS    RESTARTS   AGE\nmypod      1/1     Running   0          10d"}

        result = handle_get("test-context", "pods", name="mypod", namespace="default",
                            output="wide")

        assert result["success"] is True
        assert "prune" not in str(mock_run.call_args)
        assert isinstance(result["data"]["output"], str)

    @patch("src.k8s_mcp.tools.get.resolve")
    def test_nested_brace_jsonpath_template_rejected(self, mock_resolve, pod_meta):
        mock_resolve.return_value = pod_meta

        result = handle_get("test-context", "pods", namespace="default",
                            jsonpath_template="{.items[*].{involvedObject.kind,involvedObject.name}}")

        assert result["success"] is False
        assert result["error"] == "invalid_jsonpath_template"
        assert "Nested braces" in result.get("detail", "")
        assert "bracket-list" in result.get("detail", "")
        assert "range" in result.get("detail", "")

    @patch("src.k8s_mcp.tools.get.resolve")
    @patch("src.k8s_mcp.tools.get.run_kubectl_checked")
    def test_sibling_braces_jsonpath_template_allowed(self, mock_run, mock_resolve, pod_meta):
        mock_resolve.return_value = pod_meta
        mock_run.return_value = {"stdout": "myip"}

        result = handle_get("test-context", "pods", namespace="default",
                            jsonpath_template="{.status.podIP}{.metadata.name}")

        assert result["success"] is True
        assert result["data"]["jsonpath_template"] == "{.status.podIP}{.metadata.name}"


class TestHandleGetFullyQualifiedResource:
    """Issue 38: group-qualified resource names must reach kubectl."""

    @patch("src.k8s_mcp.tools.get.resolve")
    @patch("src.k8s_mcp.tools.get.run_kubectl_checked")
    def test_groupful_resource_uses_fully_qualified_name(self, mock_run, mock_resolve):
        node_metrics_meta = ResourceMeta(
            canonical="nodes",
            shortnames=[],
            kind="NodeMetrics",
            group="metrics.k8s.io",
            version="v1beta1",
            namespaced=False,
            verbs=["get", "list"],
        )
        mock_resolve.return_value = node_metrics_meta
        mock_run.return_value = {"stdout": '{"items": []}'}

        result = handle_get("test-context", "nodes.metrics.k8s.io")

        assert result["success"] is True
        args = mock_run.call_args[0][1]
        assert args == ["get", "nodes.metrics.k8s.io"]

    @patch("src.k8s_mcp.tools.get.resolve")
    @patch("src.k8s_mcp.tools.get.run_kubectl_checked")
    def test_groupless_resource_uses_plain_canonical(self, mock_run, mock_resolve, pod_meta):
        mock_resolve.return_value = pod_meta
        mock_run.return_value = {"stdout": '{"items": []}'}

        result = handle_get("test-context", "pods", namespace="default")

        assert result["success"] is True
        args = mock_run.call_args[0][1]
        assert args[1] == "pods"
