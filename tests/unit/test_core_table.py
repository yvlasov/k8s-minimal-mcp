"""Tests for resolution/core_table.py — real TOML file loading."""

from __future__ import annotations

import pytest

from src.k8s_mcp.resolution.core_table import load_core_table


class TestLoadCoreTable:
    def test_returns_non_empty_list(self):
        result = load_core_table()
        assert isinstance(result, list)
        assert len(result) > 0

    def test_contains_pods(self):
        result = load_core_table()
        pods = next((r for r in result if r.canonical == "pods"), None)
        assert pods is not None
        assert pods.kind == "Pod"
        assert pods.group == ""
        assert pods.version == "v1"
        assert pods.namespaced is True

    def test_contains_deployments(self):
        result = load_core_table()
        deployments = next((r for r in result if r.canonical == "deployments"), None)
        assert deployments is not None
        assert deployments.kind == "Deployment"
        assert deployments.group == "apps"
        assert deployments.version == "v1"

    def test_contains_services(self):
        result = load_core_table()
        services = next((r for r in result if r.canonical == "services"), None)
        assert services is not None
        assert services.kind == "Service"
        assert services.group == ""
        assert services.version == "v1"

    def test_contains_events(self):
        result = load_core_table()
        events = next((r for r in result if r.canonical == "events"), None)
        assert events is not None
        assert events.kind == "Event"
        assert events.group == ""
        assert events.version == "v1"
        assert events.namespaced is True
        assert events.verbs == ["get"]
        assert "ev" in events.shortnames

    def test_all_resources_have_required_fields(self):
        result = load_core_table()
        for r in result:
            assert r.canonical
            assert r.kind
            assert r.version
            assert r.namespaced is not None
            assert isinstance(r.verbs, list)
