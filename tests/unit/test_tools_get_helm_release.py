"""Tests for tools/get_helm_release.py — handle_get_helm_release (FR12)."""

from __future__ import annotations

import base64
import gzip
import json
from unittest.mock import patch

import pytest

from src.k8s_mcp.tools.get_helm_release import handle_get_helm_release
from src.k8s_mcp.resolution.models import ResourceMeta


def _encode_release(data: dict) -> str:
    """Encode a dict as base64(gzip(json)) — the Helm v3 wire format."""
    raw = json.dumps(data).encode("utf-8")
    compressed = gzip.compress(raw)
    return base64.b64encode(compressed).decode("ascii")


def _helm_secret(release: str, revision: int, data: dict) -> dict:
    """Build a Kubernetes Secret object with Helm labels."""
    return {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {
            "name": f"sh.helm.release.v1.{release}.v{revision}",
            "namespace": "default",
            "labels": {
                "owner": "helm",
                "name": release,
                "version": str(revision),
            },
        },
        "data": {"release": _encode_release(data)},
    }


def _listing_stdout(items: list[dict]) -> dict:
    return {"stdout": json.dumps({"apiVersion": "v1", "kind": "List", "items": items})}


def _release_data(
    name: str = "myapp",
    status: str = "deployed",
    chart_name: str = "myapp-chart",
    chart_version: str = "1.2.3",
    app_version: str = "4.5.6",
    values: dict | None = None,
    manifest: str = "apiVersion: apps/v1\nkind: Deployment\n",
) -> dict:
    return {
        "info": {
            "name": name,
            "status": status,
            "firstDeployed": "2024-01-01T00:00:00Z",
            "lastDeployed": "2024-06-01T00:00:00Z",
        },
        "chart": {
            "metadata": {
                "name": chart_name,
                "version": chart_version,
                "appVersion": app_version,
            }
        },
        "values": values or {"replicaCount": 2},
        "manifest": manifest,
    }


@pytest.fixture
def secret_meta():
    return ResourceMeta(
        canonical="secrets",
        shortnames=[],
        kind="Secret",
        group="",
        version="v1",
        namespaced=True,
        verbs=["get", "apply", "patch", "delete"],
    )


class TestHandleGetHelmRelease:
    @patch("src.k8s_mcp.tools.get_helm_release.resolve")
    @patch("src.k8s_mcp.tools.get_helm_release.run_kubectl_checked")
    def test_happy_path_default_revision(self, mock_run, mock_resolve, secret_meta):
        mock_resolve.return_value = secret_meta
        items = [
            _helm_secret("myapp", 1, _release_data(status="superseded")),
            _helm_secret("myapp", 2, _release_data(status="deployed")),
        ]
        mock_run.return_value = _listing_stdout(items)

        result = handle_get_helm_release("test-context", "myapp", "default")

        assert result["success"] is True
        data = result["data"]
        assert data["release"] == "myapp"
        assert data["revision"] == 2
        assert data["chart"] == "myapp-chart"
        assert data["chart_version"] == "1.2.3"
        assert data["app_version"] == "4.5.6"
        assert data["status"] == "deployed"
        assert data["values"] == {"replicaCount": 2}
        assert "manifest" not in data
        # Verify the kubectl command used Helm labels
        args = mock_run.call_args[0][1]
        assert "-l" in args
        assert "owner=helm,name=myapp" in args
        assert "-n" in args
        assert "default" in args

    @patch("src.k8s_mcp.tools.get_helm_release.resolve")
    @patch("src.k8s_mcp.tools.get_helm_release.run_kubectl_checked")
    def test_specific_revision(self, mock_run, mock_resolve, secret_meta):
        mock_resolve.return_value = secret_meta
        items = [
            _helm_secret("myapp", 1, _release_data(status="deployed")),
            _helm_secret("myapp", 2, _release_data(status="deployed")),
        ]
        mock_run.return_value = _listing_stdout(items)

        result = handle_get_helm_release("test-context", "myapp", "default", revision=1)

        assert result["success"] is True
        assert result["data"]["revision"] == 1

    @patch("src.k8s_mcp.tools.get_helm_release.resolve")
    @patch("src.k8s_mcp.tools.get_helm_release.run_kubectl_checked")
    def test_include_manifest_true(self, mock_run, mock_resolve, secret_meta):
        mock_resolve.return_value = secret_meta
        manifest = "apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: test\n"
        items = [_helm_secret("myapp", 1, _release_data(manifest=manifest))]
        mock_run.return_value = _listing_stdout(items)

        result = handle_get_helm_release("test-context", "myapp", "default", include_manifest=True)

        assert result["success"] is True
        assert result["data"]["manifest"] == manifest

    @patch("src.k8s_mcp.tools.get_helm_release.resolve")
    @patch("src.k8s_mcp.tools.get_helm_release.run_kubectl_checked")
    def test_include_manifest_false_omits_manifest(self, mock_run, mock_resolve, secret_meta):
        mock_resolve.return_value = secret_meta
        items = [_helm_secret("myapp", 1, _release_data())]
        mock_run.return_value = _listing_stdout(items)

        result = handle_get_helm_release("test-context", "myapp", "default")

        assert result["success"] is True
        assert "manifest" not in result["data"]

    @patch("src.k8s_mcp.tools.get_helm_release.resolve")
    @patch("src.k8s_mcp.tools.get_helm_release.run_kubectl_checked")
    def test_release_not_found(self, mock_run, mock_resolve, secret_meta):
        mock_resolve.return_value = secret_meta
        mock_run.return_value = _listing_stdout([])

        result = handle_get_helm_release("test-context", "nonexistent", "default")

        assert result["success"] is False
        assert result["error"] == "helm_release_not_found"
        assert result["release"] == "nonexistent"
        assert result["namespace"] == "default"

    @patch("src.k8s_mcp.tools.get_helm_release.resolve")
    @patch("src.k8s_mcp.tools.get_helm_release.run_kubectl_checked")
    def test_revision_not_found(self, mock_run, mock_resolve, secret_meta):
        mock_resolve.return_value = secret_meta
        items = [_helm_secret("myapp", 1, _release_data())]
        mock_run.return_value = _listing_stdout(items)

        result = handle_get_helm_release("test-context", "myapp", "default", revision=99)

        assert result["success"] is False
        assert result["error"] == "helm_release_not_found"

    @patch("src.k8s_mcp.tools.get_helm_release.resolve")
    @patch("src.k8s_mcp.tools.get_helm_release.run_kubectl_checked")
    def test_decode_failed_base64_stage(self, mock_run, mock_resolve, secret_meta):
        mock_resolve.return_value = secret_meta
        secret = _helm_secret("myapp", 1, _release_data())
        # Corrupt the base64 value
        secret["data"]["release"] = "not-valid-base64!!!"
        mock_run.return_value = _listing_stdout([secret])

        result = handle_get_helm_release("test-context", "myapp", "default")

        assert result["success"] is False
        assert result["error"] == "helm_release_decode_failed"
        assert result["stage"] == "base64"

    @patch("src.k8s_mcp.tools.get_helm_release.resolve")
    @patch("src.k8s_mcp.tools.get_helm_release.run_kubectl_checked")
    def test_decode_failed_gzip_stage(self, mock_run, mock_resolve, secret_meta):
        mock_resolve.return_value = secret_meta
        # Valid base64 but not valid gzip
        bad_gzip_b64 = base64.b64encode(b"not gzip data at all").decode("ascii")
        secret = _helm_secret("myapp", 1, _release_data())
        secret["data"]["release"] = bad_gzip_b64
        mock_run.return_value = _listing_stdout([secret])

        result = handle_get_helm_release("test-context", "myapp", "default")

        assert result["success"] is False
        assert result["error"] == "helm_release_decode_failed"
        assert result["stage"] == "gzip"

    @patch("src.k8s_mcp.tools.get_helm_release.resolve")
    @patch("src.k8s_mcp.tools.get_helm_release.run_kubectl_checked")
    def test_decode_failed_json_stage(self, mock_run, mock_resolve, secret_meta):
        mock_resolve.return_value = secret_meta
        # Valid base64 + valid gzip, but not valid JSON
        bad_json = gzip.compress(b"this is not json")
        bad_json_b64 = base64.b64encode(bad_json).decode("ascii")
        secret = _helm_secret("myapp", 1, _release_data())
        secret["data"]["release"] = bad_json_b64
        mock_run.return_value = _listing_stdout([secret])

        result = handle_get_helm_release("test-context", "myapp", "default")

        assert result["success"] is False
        assert result["error"] == "helm_release_decode_failed"
        assert result["stage"] == "json"

    @patch("src.k8s_mcp.tools.get_helm_release.resolve")
    @patch("src.k8s_mcp.tools.get_helm_release.run_kubectl_checked")
    def test_missing_release_key_in_data(self, mock_run, mock_resolve, secret_meta):
        mock_resolve.return_value = secret_meta
        secret = {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {
                "name": "sh.helm.release.v1.myapp.v1",
                "namespace": "default",
                "labels": {"owner": "helm", "name": "myapp", "version": "1"},
            },
            "data": {},  # No "release" key
        }
        mock_run.return_value = _listing_stdout([secret])

        result = handle_get_helm_release("test-context", "myapp", "default")

        assert result["success"] is False
        assert result["error"] == "helm_release_decode_failed"
        assert result["stage"] == "base64"

    @patch("src.k8s_mcp.tools.get_helm_release.resolve")
    @patch("src.k8s_mcp.tools.get_helm_release.run_kubectl_checked")
    def test_resolve_error_passthrough(self, mock_run, mock_resolve):
        mock_resolve.return_value = {"error": "unknown_resource", "resource": "secrets"}

        result = handle_get_helm_release("test-context", "myapp", "default")

        assert result["success"] is False
        assert result["error"] == "unknown_resource"
        mock_run.assert_not_called()

    @patch("src.k8s_mcp.tools.get_helm_release.resolve")
    @patch("src.k8s_mcp.tools.get_helm_release.run_kubectl_checked")
    def test_validate_error_passthrough(self, mock_run, mock_resolve):
        mock_resolve.return_value = ResourceMeta(
            canonical="nodes", shortnames=["no"], kind="Node", group="", version="v1",
            namespaced=False, verbs=["get"],
        )

        result = handle_get_helm_release("test-context", "myapp", "default")

        assert result["success"] is False
        assert result["error"] == "namespace_invalid"
        mock_run.assert_not_called()

    @patch("src.k8s_mcp.tools.get_helm_release.resolve")
    @patch("src.k8s_mcp.tools.get_helm_release.run_kubectl_checked")
    def test_kubectl_failure_passthrough(self, mock_run, mock_resolve, secret_meta):
        mock_resolve.return_value = secret_meta
        mock_run.return_value = {"error": "kubectl_failure", "command": ["kubectl"], "stderr": "NotFound"}

        result = handle_get_helm_release("test-context", "myapp", "default")

        assert result["success"] is False
        assert result["error"] == "kubectl_failure"
