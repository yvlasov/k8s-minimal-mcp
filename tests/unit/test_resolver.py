"""Tests for resolution/resolver.py — R2/R6 resolution logic."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.k8s_mcp.resolution import resolve, validate, ResourceMeta
from src.k8s_mcp.resolution.discovery import DiscoveryCache
from src.k8s_mcp.errors import (
    ERROR_AMBIGUOUS_RESOURCE,
    ERROR_UNKNOWN_RESOURCE,
    ERROR_VERB_UNSUPPORTED,
    ERROR_NAMESPACE_INVALID,
)


@pytest.fixture
def core_table():
    """Minimal core table for testing."""
    return [
        ResourceMeta(
            canonical="pods",
            shortnames=["po"],
            kind="Pod",
            group="",
            version="v1",
            namespaced=True,
            verbs=["get", "logs", "apply", "patch", "delete", "exec"],
        ),
        ResourceMeta(
            canonical="deployments",
            shortnames=["deploy"],
            kind="Deployment",
            group="apps",
            version="v1",
            namespaced=True,
            verbs=["get", "apply", "patch", "delete"],
        ),
        ResourceMeta(
            canonical="networkpolicies",
            shortnames=["netpol"],
            kind="NetworkPolicy",
            group="networking.k8s.io",
            version="v1",
            namespaced=True,
            verbs=["get", "apply", "patch", "delete"],
        ),
        ResourceMeta(
            canonical="persistentvolumes",
            shortnames=["pv"],
            kind="PersistentVolume",
            group="",
            version="v1",
            namespaced=False,
            verbs=["get", "apply", "patch", "delete"],
        ),
        ResourceMeta(
            canonical="events",
            shortnames=["ev"],
            kind="Event",
            group="",
            version="v1",
            namespaced=True,
            verbs=["get"],
        ),
    ]


class TestResolve:
    def test_resolve_by_canonical(self, core_table):
        result = resolve("test-context", "pods", core_table=core_table)
        assert isinstance(result, ResourceMeta)
        assert result.canonical == "pods"
        assert result.kind == "Pod"

    def test_resolve_by_shortname(self, core_table):
        result = resolve("test-context", "deploy", core_table=core_table)
        assert isinstance(result, ResourceMeta)
        assert result.canonical == "deployments"

    def test_resolve_by_kind(self, core_table):
        result = resolve("test-context", "Deployment", core_table=core_table)
        assert isinstance(result, ResourceMeta)
        assert result.kind == "Deployment"

    def test_resolve_by_fully_qualified(self, core_table):
        result = resolve("test-context", "networkpolicies.networking.k8s.io", core_table=core_table)
        assert isinstance(result, ResourceMeta)
        assert result.group == "networking.k8s.io"

    def test_resolve_events_from_core_table(self, core_table):
        result = resolve("test-context", "events", core_table=core_table)
        assert isinstance(result, ResourceMeta)
        assert result.canonical == "events"
        assert result.kind == "Event"
        assert result.group == ""
        assert result.version == "v1"
        assert result.namespaced is True
        assert result.verbs == ["get"]

    def test_resolve_events_by_shortname(self, core_table):
        result = resolve("test-context", "ev", core_table=core_table)
        assert isinstance(result, ResourceMeta)
        assert result.canonical == "events"
        assert result.kind == "Event"

    def test_resolve_case_insensitive(self, core_table):
        result = resolve("test-context", "PODS", core_table=core_table)
        assert isinstance(result, ResourceMeta)
        assert result.canonical == "pods"

    def test_resolve_unknown_resource(self, core_table):
        result = resolve("test-context", "foobar", core_table=core_table)
        assert isinstance(result, dict)
        assert result["error"] == ERROR_UNKNOWN_RESOURCE
        assert "suggestions" in result

    def test_resolve_with_discovery_cache_cold_refresh(self, core_table):
        cache = DiscoveryCache()
        crd_resource = ResourceMeta(
            canonical="customresourcedefinitions",
            shortnames=["crd"],
            kind="CustomResourceDefinition",
            group="apiextensions.k8s.io",
            version="v1",
            namespaced=False,
            verbs=["get", "list", "create", "delete"],
        )
        with patch.object(DiscoveryCache, "refresh", return_value=[crd_resource]):
            result = resolve("test-context", "customresourcedefinitions", discovery_cache=cache, core_table=core_table)
        assert isinstance(result, ResourceMeta)
        assert result.canonical == "customresourcedefinitions"

    def test_resolve_with_discovery_cache_cold_resource_not_found(self, core_table):
        cache = DiscoveryCache()
        with patch.object(DiscoveryCache, "refresh", return_value=[core_table[0]]):
            result = resolve("test-context", "customresourcedefinitions", discovery_cache=cache, core_table=core_table)
        assert isinstance(result, dict)
        assert result["error"] == ERROR_UNKNOWN_RESOURCE


class TestValidate:
    def test_validate_verb_supported(self, core_table):
        pod = core_table[0]
        result = validate(pod, "get", "default")
        assert result is None

    def test_validate_verb_unsupported(self, core_table):
        deploy = core_table[1]
        result = validate(deploy, "exec", "default")
        assert isinstance(result, dict)
        assert result["error"] == ERROR_VERB_UNSUPPORTED

    def test_validate_namespaced_with_ns(self, core_table):
        pod = core_table[0]
        result = validate(pod, "get", "default")
        assert result is None

    def test_validate_namespaced_without_ns(self, core_table):
        pod = core_table[0]
        result = validate(pod, "get", None)
        assert isinstance(result, dict)
        assert result["error"] == ERROR_NAMESPACE_INVALID

    def test_validate_cluster_scoped_without_ns(self, core_table):
        pv = core_table[3]
        result = validate(pv, "get", None)
        assert result is None

    def test_validate_cluster_scoped_with_ns(self, core_table):
        pv = core_table[3]
        result = validate(pv, "get", "default")
        assert isinstance(result, dict)
        assert result["error"] == ERROR_NAMESPACE_INVALID

    def test_validate_namespaced_with_all_namespaces(self, core_table):
        pod = core_table[0]
        result = validate(pod, "get", None, all_namespaces=True)
        assert result is None

    def test_validate_namespaced_without_all_namespaces_still_rejects(self, core_table):
        pod = core_table[0]
        result = validate(pod, "get", None, all_namespaces=False)
        assert isinstance(result, dict)
        assert result["error"] == ERROR_NAMESPACE_INVALID
