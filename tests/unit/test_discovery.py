"""Tests for discovery cache parser (Issue 9)."""

import pytest

from src.k8s_mcp.resolution.discovery import _parse_api_resources
from src.k8s_mcp.resolution.models import ResourceMeta

FIXTURE_PATH = "tests/fixtures/kubectl_outputs/api_resources_wide.txt"


def _load_fixture() -> str:
    with open(FIXTURE_PATH) as f:
        return f.read()


class TestParseApiResources:
    def test_parses_core_resources(self):
        result = _parse_api_resources(_load_fixture())
        pods = next((r for r in result if r.canonical == "pods"), None)
        assert pods is not None
        assert pods.kind == "Pod"
        assert pods.group == ""
        assert pods.version == "v1"
        assert pods.namespaced is True
        assert "po" in pods.shortnames
        assert "get" in pods.verbs
        assert "create" in pods.verbs
        assert "delete" in pods.verbs

    def test_parses_apps_resources(self):
        result = _parse_api_resources(_load_fixture())
        deployments = next((r for r in result if r.canonical == "deployments"), None)
        assert deployments is not None
        assert deployments.kind == "Deployment"
        assert deployments.group == "apps"
        assert deployments.version == "v1"
        assert deployments.namespaced is True
        assert "deploy" in deployments.shortnames

    def test_parses_crd_resources(self):
        result = _parse_api_resources(_load_fixture())
        cilium_netpol = next(
            (r for r in result if r.canonical == "ciliumnetworkpolicies"), None
        )
        assert cilium_netpol is not None
        assert cilium_netpol.kind == "CiliumNetworkPolicy"
        assert cilium_netpol.group == "cilium.io"
        assert cilium_netpol.version == "v2"
        assert cilium_netpol.namespaced is True
        assert "ciliumnet" in cilium_netpol.shortnames

    def test_parses_cluster_scoped_resources(self):
        result = _parse_api_resources(_load_fixture())
        namespaces = next((r for r in result if r.canonical == "namespaces"), None)
        assert namespaces is not None
        assert namespaces.namespaced is False
        assert namespaces.group == ""
        assert namespaces.version == "v1"

    def test_parses_customresourcedefinitions(self):
        result = _parse_api_resources(_load_fixture())
        crd = next((r for r in result if r.canonical == "customresourcedefinitions"), None)
        assert crd is not None
        assert crd.kind == "CustomResourceDefinition"
        assert crd.group == "apiextensions.k8s.io"
        assert crd.version == "v1"
        assert crd.namespaced is False

    def test_parses_networking_resources(self):
        result = _parse_api_resources(_load_fixture())
        ingress = next((r for r in result if r.canonical == "ingresses"), None)
        assert ingress is not None
        assert ingress.kind == "Ingress"
        assert ingress.group == "networking.k8s.io"
        assert ingress.version == "v1"
        assert ingress.namespaced is True
        assert "ing" in ingress.shortnames

    def test_skips_componentstatuses(self):
        result = _parse_api_resources(_load_fixture())
        cs = [r for r in result if r.canonical in ("componentstatuses", "cs")]
        assert len(cs) == 0

    def test_parses_verbs_correctly(self):
        result = _parse_api_resources(_load_fixture())
        pods = next((r for r in result if r.canonical == "pods"), None)
        assert pods is not None
        expected_verbs = {"create", "delete", "deletecollection", "get", "list", "patch", "update", "watch"}
        assert set(pods.verbs) == expected_verbs

    def test_parses_empty_output(self):
        result = _parse_api_resources("")
        assert result == []

    def test_parses_header_only(self):
        output = "NAME SHORTNAMES APIVERSION NAMESPACED KIND VERBS CATEGORIES\n"
        result = _parse_api_resources(output)
        assert result == []

    def test_parses_with_separator_line(self):
        output = """NAME SHORTNAMES APIVERSION NAMESPACED KIND VERBS
---
pods po v1 true Pod get,list"""
        result = _parse_api_resources(output)
        assert len(result) == 1
        assert result[0].canonical == "pods"
        assert result[0].group == ""
        assert result[0].version == "v1"
        assert result[0].namespaced is True
        assert result[0].verbs == ["get", "list"]

    def test_parses_without_separator_line(self):
        output = """NAME SHORTNAMES APIVERSION NAMESPACED KIND VERBS
pods po v1 true Pod get,list"""
        result = _parse_api_resources(output)
        assert len(result) == 1
        assert result[0].canonical == "pods"

    def test_parses_resource_without_shortnames(self):
        result = _parse_api_resources(_load_fixture())
        pod_templates = next(
            (r for r in result if r.canonical == "podtemplates"), None
        )
        assert pod_templates is not None
        assert pod_templates.shortnames == []

    def test_parses_resource_without_categories(self):
        result = _parse_api_resources(_load_fixture())
        # ciliumnetworkpolicies has no CATEGORIES column in fixture
        cilium_netpol = next(
            (r for r in result if r.canonical == "ciliumnetworkpolicies"), None
        )
        assert cilium_netpol is not None
        assert cilium_netpol.kind == "CiliumNetworkPolicy"

    def test_total_resource_count(self):
        result = _parse_api_resources(_load_fixture())
        # Should have all resources except componentstatuses
        assert len(result) == 27  # 28 data rows - 1 componentstatuses

    def test_all_resources_have_required_fields(self):
        result = _parse_api_resources(_load_fixture())
        for r in result:
            assert isinstance(r, ResourceMeta)
            assert r.canonical
            assert r.kind
            assert r.version
            assert isinstance(r.namespaced, bool)
            assert isinstance(r.verbs, list)
            assert len(r.verbs) > 0


class TestDiscoveryCacheRefresh:
    def test_refresh_returns_error_on_empty_output(self, mocker):
        from src.k8s_mcp.resolution.discovery import DiscoveryCache
        from src.k8s_mcp.errors import ERROR_DISCOVERY_FAILURE
        cache = DiscoveryCache()
        mocker.patch("src.k8s_mcp.resolution.discovery.run_kubectl", return_value={"stdout": "", "error": None})
        result = cache.refresh("test-context")
        assert isinstance(result, dict)
        assert result["error"] == ERROR_DISCOVERY_FAILURE
        assert "detail" in result

    def test_refresh_succeeds_with_valid_output(self, mocker):
        from src.k8s_mcp.resolution.discovery import DiscoveryCache
        cache = DiscoveryCache()
        fixture = _load_fixture()
        mocker.patch("src.k8s_mcp.resolution.discovery.run_kubectl", return_value={"stdout": fixture, "error": None})
        result = cache.refresh("test-context")
        assert isinstance(result, list)
        assert len(result) > 0
        pods = next((r for r in result if r.canonical == "pods"), None)
        assert pods is not None
