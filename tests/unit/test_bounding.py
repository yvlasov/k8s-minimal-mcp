"""Tests for output/bounding.py — R10 defaults + R4 reporting."""

from __future__ import annotations

import pytest

from src.k8s_mcp.output.bounding import bound_get_names, bound_logs, _extract_identity


class TestBoundGetNames:
    def test_single_resource(self):
        data = {
            "kind": "Pod",
            "metadata": {"name": "test-pod", "namespace": "default"},
        }
        result = bound_get_names(data)
        assert result["_bound"]["output"] == "name"
        assert result["_bound"]["truncated"] is True
        assert len(result["items"]) == 1
        assert result["items"][0]["name"] == "test-pod"
        assert result["items"][0]["namespace"] == "default"
        assert result["items"][0]["kind"] == "Pod"

    def test_list_type(self):
        data = {
            "kind": "PodList",
            "items": [
                {"kind": "Pod", "metadata": {"name": "pod-1", "namespace": "default"}},
                {"kind": "Pod", "metadata": {"name": "pod-2", "namespace": "kube-system"}},
            ],
        }
        result = bound_get_names(data)
        assert len(result["items"]) == 2
        assert result["items"][0]["name"] == "pod-1"
        assert result["items"][1]["name"] == "pod-2"

    def test_list_without_list_kind(self):
        data = [
            {"kind": "Pod", "metadata": {"name": "pod-1"}},
            {"kind": "Pod", "metadata": {"name": "pod-2"}},
        ]
        result = bound_get_names(data)
        assert len(result["items"]) == 2

    def test_empty_data(self):
        result = bound_get_names({})
        assert result["items"] == []
        assert result["_bound"]["truncated"] is True


class TestBoundLogs:
    def test_tail_limit(self):
        stdout = "\n".join(f"line-{i}" for i in range(100))
        result = bound_logs(stdout, tail=10)
        assert result["_bound"]["tail"] == 10
        assert result["_bound"]["total_lines"] == 100
        assert result["_bound"]["truncated"] is True
        lines = result["logs"].splitlines()
        assert len(lines) == 10
        assert lines[0] == "line-90"

    def test_no_tail(self):
        stdout = "line-1\nline-2\nline-3"
        result = bound_logs(stdout)
        assert result["_bound"]["truncated"] is False
        assert result["logs"] == stdout

    def test_tail_larger_than_lines(self):
        stdout = "line-1\nline-2"
        result = bound_logs(stdout, tail=100)
        assert result["_bound"]["truncated"] is False
        assert result["logs"] == stdout

    def test_empty_logs(self):
        result = bound_logs("")
        assert result["logs"] == ""
        assert result["_bound"]["truncated"] is False


class TestExtractIdentity:
    def test_full_metadata(self):
        obj = {"kind": "Pod", "metadata": {"name": "my-pod", "namespace": "test"}}
        result = _extract_identity(obj)
        assert result == {"name": "my-pod", "namespace": "test", "kind": "Pod"}

    def test_no_namespace(self):
        obj = {"kind": "Node", "metadata": {"name": "node-1"}}
        result = _extract_identity(obj)
        assert result["namespace"] is None

    def test_no_metadata(self):
        obj = {"kind": "Pod"}
        result = _extract_identity(obj)
        assert result["name"] == ""
        assert result["kind"] == "Pod"

    def test_non_dict(self):
        assert _extract_identity("string") == {}
        assert _extract_identity(None) == {}
