"""Tests for tools/list_resources.py — handle_list_resources."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.k8s_mcp.tools.list_resources import (
    handle_list_resources,
    _filter_resources,
    _serialize_resource,
)
from src.k8s_mcp.resolution.models import ResourceMeta


@pytest.fixture
def sample_resources():
    return [
        ResourceMeta(
            canonical="pods",
            shortnames=["po"],
            kind="Pod",
            group="",
            version="v1",
            namespaced=True,
            verbs=["get", "list", "watch"],
        ),
        ResourceMeta(
            canonical="deployments",
            shortnames=["deploy"],
            kind="Deployment",
            group="apps",
            version="v1",
            namespaced=True,
            verbs=["get", "list", "watch", "create", "delete"],
        ),
        ResourceMeta(
            canonical="networkpolicies",
            shortnames=["netpol"],
            kind="NetworkPolicy",
            group="networking.k8s.io",
            version="v1",
            namespaced=True,
            verbs=["get", "list", "watch", "create", "delete"],
        ),
    ]


class TestFilterResources:
    def test_no_filter_returns_all(self, sample_resources):
        result = _filter_resources(sample_resources, None)
        assert len(result) == 3

    def test_filter_by_canonical(self, sample_resources):
        result = _filter_resources(sample_resources, "deploy")
        assert len(result) == 1
        assert result[0].canonical == "deployments"

    def test_filter_by_kind(self, sample_resources):
        result = _filter_resources(sample_resources, "pod")
        assert len(result) == 1
        assert result[0].kind == "Pod"

    def test_filter_by_group(self, sample_resources):
        result = _filter_resources(sample_resources, "networking")
        assert len(result) == 1
        assert result[0].group == "networking.k8s.io"

    def test_filter_case_insensitive(self, sample_resources):
        result = _filter_resources(sample_resources, "DEPLOY")
        assert len(result) == 1
        assert result[0].canonical == "deployments"

    def test_filter_no_match(self, sample_resources):
        result = _filter_resources(sample_resources, "nonexistent")
        assert len(result) == 0

    def test_filter_empty_string(self, sample_resources):
        result = _filter_resources(sample_resources, "")
        assert len(result) == 3

    def test_filter_by_shortname_not_included(self, sample_resources):
        # shortnames are NOT part of the filter per SPEC (only canonical, kind, group)
        # "netpol" doesn't appear in canonical/kind/group of any resource
        result = _filter_resources(sample_resources, "netpol")
        assert len(result) == 0


class TestSerializeResource:
    def test_serialize_core_resource(self):
        r = ResourceMeta(
            canonical="pods",
            shortnames=["po"],
            kind="Pod",
            group="",
            version="v1",
            namespaced=True,
            verbs=["get", "list"],
        )
        result = _serialize_resource(r)
        assert result == {
            "name": "pods",
            "shortnames": ["po"],
            "kind": "Pod",
            "api_version": "v1",
            "namespaced": True,
            "verbs": ["get", "list"],
        }

    def test_serialize_group_resource(self):
        r = ResourceMeta(
            canonical="deployments",
            shortnames=["deploy"],
            kind="Deployment",
            group="apps",
            version="v1",
            namespaced=True,
            verbs=["get", "list"],
        )
        result = _serialize_resource(r)
        assert result["api_version"] == "apps/v1"


class TestHandleListResources:
    @patch("src.k8s_mcp.tools.list_resources.DiscoveryCache")
    def test_cache_hit_path(self, mock_cache_class, sample_resources):
        mock_cache = MagicMock()
        mock_cache.get.return_value = sample_resources
        mock_cache.refresh.return_value = []

        result = handle_list_resources("test-context", discovery_cache=mock_cache)

        assert result["success"] is True
        assert result["data"]["count"] == 3
        mock_cache.get.assert_called_once_with("test-context")
        mock_cache.refresh.assert_not_called()

    @patch("src.k8s_mcp.tools.list_resources.DiscoveryCache")
    def test_cache_miss_path(self, mock_cache_class, sample_resources):
        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        mock_cache.refresh.return_value = sample_resources

        result = handle_list_resources("test-context", discovery_cache=mock_cache)

        assert result["success"] is True
        assert result["data"]["count"] == 3
        mock_cache.get.assert_called_once_with("test-context")
        mock_cache.refresh.assert_called_once_with("test-context")

    @patch("src.k8s_mcp.tools.list_resources.DiscoveryCache")
    def test_refresh_error_propagates(self, mock_cache_class):
        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        mock_cache.refresh.return_value = {"error": "kubectl_failure", "detail": "forbidden"}

        result = handle_list_resources("test-context", discovery_cache=mock_cache)

        assert result["success"] is False
        assert result["error"] == "kubectl_failure"

    @patch("src.k8s_mcp.tools.list_resources.DiscoveryCache")
    def test_search_filter_applied(self, mock_cache_class, sample_resources):
        mock_cache = MagicMock()
        mock_cache.get.return_value = sample_resources

        result = handle_list_resources("test-context", search="deploy", discovery_cache=mock_cache)

        assert result["success"] is True
        assert result["data"]["count"] == 1
        assert result["data"]["resources"][0]["name"] == "deployments"

    def test_no_discovery_cache_returns_empty(self):
        result = handle_list_resources("test-context", discovery_cache=None)

        assert result["success"] is True
        assert result["data"]["count"] == 0
        assert result["data"]["resources"] == []

    @patch("src.k8s_mcp.tools.list_resources.DiscoveryCache")
    def test_response_shape_matches_spec(self, mock_cache_class, sample_resources):
        mock_cache = MagicMock()
        mock_cache.get.return_value = sample_resources[:1]

        result = handle_list_resources("test-context", discovery_cache=mock_cache)

        assert result["success"] is True
        assert "resources" in result["data"]
        assert "count" in result["data"]
        assert result["data"]["count"] == 1

        resource = result["data"]["resources"][0]
        assert set(resource.keys()) == {"name", "shortnames", "kind", "api_version", "namespaced", "verbs"}

    @patch("src.k8s_mcp.tools.list_resources.DiscoveryCache")
    def test_context_echoed_in_envelope(self, mock_cache_class, sample_resources):
        mock_cache = MagicMock()
        mock_cache.get.return_value = sample_resources

        result = handle_list_resources("my-context", discovery_cache=mock_cache)

        assert result["context"] == "my-context"
        assert result["tool"] == "k_list_resources"
