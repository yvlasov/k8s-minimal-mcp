"""Tests for output/pruning.py — R9 field stripping."""

from __future__ import annotations

import pytest

from src.k8s_mcp.output.pruning import prune


@pytest.fixture
def full_pod():
    return {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {
            "name": "test-pod",
            "namespace": "default",
            "uid": "abc-123",
            "generation": 1,
            "resourceVersion": "98765",
            "managedFields": [{"manager": "kubectl", "operation": "Update"}],
            "annotations": {
                "kubectl.kubernetes.io/last-applied-configuration": '{"apiVersion":"v1"}',
                "other-annotation": "keep-me",
            },
        },
        "status": {
            "phase": "Running",
            "containerStatuses": [{"ready": True}],
        },
        "spec": {
            "containers": [{"name": "app", "image": "nginx"}],
        },
    }


@pytest.fixture
def full_configmap():
    return {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {
            "name": "test-cm",
            "uid": "xyz-789",
            "generation": 2,
            "resourceVersion": "54321",
            "managedFields": [],
        },
        "data": {"key": "value"},
        "status": {"should": "be-stripped"},
    }


class TestPrune:
    def test_prune_strips_uid(self, full_pod):
        result = prune(full_pod, kind="Pod")
        assert "uid" not in result.get("metadata", {})

    def test_prune_strips_generation(self, full_pod):
        result = prune(full_pod, kind="Pod")
        assert "generation" not in result.get("metadata", {})

    def test_prune_strips_resource_version(self, full_pod):
        result = prune(full_pod, kind="Pod")
        assert "resourceVersion" not in result.get("metadata", {})

    def test_prune_strips_managed_fields(self, full_pod):
        result = prune(full_pod, kind="Pod")
        assert "managedFields" not in result.get("metadata", {})

    def test_prune_strips_last_applied_config(self, full_pod):
        result = prune(full_pod, kind="Pod")
        annotations = result.get("metadata", {}).get("annotations", {})
        assert "kubectl.kubernetes.io/last-applied-configuration" not in annotations

    def test_prune_keeps_other_annotations(self, full_pod):
        result = prune(full_pod, kind="Pod")
        annotations = result.get("metadata", {}).get("annotations", {})
        assert annotations.get("other-annotation") == "keep-me"

    def test_prune_keeps_status_for_pod(self, full_pod):
        result = prune(full_pod, kind="Pod")
        assert "status" in result
        assert result["status"]["phase"] == "Running"

    def test_prune_strips_status_for_configmap(self, full_configmap):
        result = prune(full_configmap, kind="ConfigMap")
        assert "status" not in result

    def test_prune_keeps_status_when_requested(self, full_configmap):
        result = prune(full_configmap, kind="ConfigMap", keep_status=True)
        assert "status" in result
        assert result["status"]["should"] == "be-stripped"

    def test_prune_non_dict_unchanged(self):
        assert prune("string") == "string"
        assert prune(42) == 42
        assert prune([1, 2, 3]) == [1, 2, 3]

    def test_prune_preserves_spec(self, full_pod):
        result = prune(full_pod, kind="Pod")
        assert result["spec"]["containers"][0]["name"] == "app"

    def test_prune_preserves_api_version(self, full_pod):
        result = prune(full_pod, kind="Pod")
        assert result["apiVersion"] == "v1"
