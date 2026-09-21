"""Tests for output/envelope.py — R3 context echo."""

from __future__ import annotations

import pytest

from src.k8s_mcp.output.envelope import envelope, envelope_list_contexts


class TestEnvelope:
    def test_success_envelope(self):
        result = envelope({"items": [{"name": "pod-1"}]}, "prod", "k_get")
        assert result["context"] == "prod"
        assert result["tool"] == "k_get"
        assert result["success"] is True
        assert result["data"]["items"][0]["name"] == "pod-1"

    def test_error_envelope(self):
        err_data = {"error": "unknown_resource", "context": "dev", "resource": "foobar"}
        result = envelope(err_data, "dev", "k_get", success=False)
        assert result["context"] == "dev"
        assert result["tool"] == "k_get"
        assert result["success"] is False
        assert result["error"] == "unknown_resource"

    def test_error_envelope_string(self):
        result = envelope("something went wrong", "dev", "k_get", success=False)
        assert result["success"] is False
        assert result["error"] == "something went wrong"


class TestEnvelopeListContexts:
    def test_list_contexts(self):
        result = envelope_list_contexts(["prod-eu", "dev-us", "staging"], "default")
        assert result["context"] == "default"
        assert result["tool"] == "k_list_contexts"
        assert result["success"] is True
        assert result["data"]["contexts"] == ["prod-eu", "dev-us", "staging"]
        assert result["data"]["count"] == 3

    def test_empty_contexts(self):
        result = envelope_list_contexts([], "default")
        assert result["data"]["contexts"] == []
        assert result["data"]["count"] == 0
