"""Tests for errors.py — §7 error contract shape."""

from __future__ import annotations

import pytest

from src.k8s_mcp.errors import (
    ambiguous_resource,
    unknown_resource,
    verb_unsupported,
    namespace_invalid,
    unknown_context,
    access_denied,
    kubectl_failure,
    exec_failed,
    object_not_found,
    ERROR_AMBIGUOUS_RESOURCE,
    ERROR_UNKNOWN_RESOURCE,
    ERROR_VERB_UNSUPPORTED,
    ERROR_NAMESPACE_INVALID,
    ERROR_UNKNOWN_CONTEXT,
    ERROR_ACCESS_DENIED,
    ERROR_KUBECTL_FAILURE,
    ERROR_EXEC_FAILED,
    ERROR_OBJECT_NOT_FOUND,
)


class TestErrorShapes:
    def test_ambiguous_resource(self):
        err = ambiguous_resource("prod", ["policies.kyverno.io", "authorizationpolicies.security.istio.io"])
        assert err["context"] == "prod"
        assert err["error"] == ERROR_AMBIGUOUS_RESOURCE
        assert err["candidates"] == ["policies.kyverno.io", "authorizationpolicies.security.istio.io"]
        assert "hint" in err

    def test_unknown_resource(self):
        err = unknown_resource("dev", "foobar", suggestions=["pods", "services"])
        assert err["context"] == "dev"
        assert err["error"] == ERROR_UNKNOWN_RESOURCE
        assert err["resource"] == "foobar"
        assert err["suggestions"] == ["pods", "services"]

    def test_unknown_resource_no_suggestions(self):
        err = unknown_resource("dev", "foobar")
        assert "suggestions" not in err

    def test_verb_unsupported(self):
        err = verb_unsupported("prod", "pods", "apply")
        assert err["error"] == ERROR_VERB_UNSUPPORTED
        assert err["resource"] == "pods"
        assert err["verb"] == "apply"

    def test_namespace_invalid(self):
        err = namespace_invalid("prod", "PersistentVolume", detail="cluster-scoped")
        assert err["error"] == ERROR_NAMESPACE_INVALID
        assert err["resource"] == "PersistentVolume"
        assert err["detail"] == "cluster-scoped"

    def test_unknown_context(self):
        err = unknown_context("wrong-context", ["prod-eu", "dev-us", "staging"])
        assert err["error"] == ERROR_UNKNOWN_CONTEXT
        assert err["valid_contexts"] == ["prod-eu", "dev-us", "staging"]

    def test_access_denied(self):
        err = access_denied("prod", "delete", "readonly")
        assert err["error"] == ERROR_ACCESS_DENIED
        assert err["verb"] == "delete"
        assert err["access_level"] == "readonly"

    def test_kubectl_failure(self):
        err = kubectl_failure("prod", "kubectl get foobar", "NotFound: foobar", exit_code=1)
        assert err["error"] == ERROR_KUBECTL_FAILURE
        assert err["command"] == "kubectl get foobar"
        assert err["exit_code"] == 1

    def test_exec_failed(self):
        err = exec_failed("prod", "my-pod", "default", ["ls", "/nonexistent"],
                          stderr="no such file", exit_code=1)
        assert err["error"] == ERROR_EXEC_FAILED
        assert err["pod"] == "my-pod"
        assert err["namespace"] == "default"
        assert err["command"] == ["ls", "/nonexistent"]
        assert err["stderr"] == "no such file"
        assert err["exit_code"] == 1

    def test_object_not_found_with_all_fields(self):
        err = object_not_found("dev", "pods", name="kubelet", raw_stderr='Error from server (NotFound): pods "kubelet" not found')
        assert err["error"] == ERROR_OBJECT_NOT_FOUND
        assert err["context"] == "dev"
        assert err["resource"] == "pods"
        assert err["name"] == "kubelet"
        assert err["raw_stderr"] == 'Error from server (NotFound): pods "kubelet" not found'

    def test_object_not_found_minimal(self):
        err = object_not_found("dev")
        assert err["error"] == ERROR_OBJECT_NOT_FOUND
        assert err["context"] == "dev"
        assert "resource" not in err
        assert "name" not in err
        assert "raw_stderr" not in err

    def test_object_not_found_with_resource_only(self):
        err = object_not_found("dev", "secrets")
        assert err["error"] == ERROR_OBJECT_NOT_FOUND
        assert err["resource"] == "secrets"
        assert "name" not in err
        assert "raw_stderr" not in err

    def test_all_error_codes_defined(self):
        """Ensure all error code constants are non-empty strings."""
        for name, value in globals().items():
            if name.startswith("ERROR_"):
                assert isinstance(value, str)
                assert len(value) > 0
