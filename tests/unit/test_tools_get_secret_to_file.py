"""Tests for tools/get_secret_to_file.py — handle_get_secret_to_file (FR9)."""

from __future__ import annotations

import base64
import json
import os
from unittest.mock import patch

import pytest

from src.k8s_mcp.tools.get_secret_to_file import handle_get_secret_to_file
from src.k8s_mcp.resolution.models import ResourceMeta


def _b64(value: str) -> str:
    return base64.b64encode(value.encode("utf-8")).decode("ascii")


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


def _secret_stdout(data: dict[str, str]) -> dict:
    return {"stdout": json.dumps({"apiVersion": "v1", "kind": "Secret", "data": data})}


class TestHandleGetSecretToFile:
    @patch("src.k8s_mcp.tools.get_secret_to_file.resolve")
    @patch("src.k8s_mcp.tools.get_secret_to_file.run_kubectl_checked")
    def test_happy_path_writes_decoded_values(self, mock_run, mock_resolve, secret_meta, tmp_path):
        mock_resolve.return_value = secret_meta
        mock_run.return_value = _secret_stdout({"username": _b64("admin"), "password": _b64("s3cr3t-pw")})
        dst = tmp_path / "secret.json"

        result = handle_get_secret_to_file("test-context", "my-secret", "default", str(dst))

        assert result["success"] is True
        assert result["data"]["written_to"] == str(dst)
        assert result["data"]["keys"] == ["username", "password"]
        written = json.loads(dst.read_text())
        assert written["data"] == {"username": "admin", "password": "s3cr3t-pw"}
        assert written["base64_keys"] == []
        args = mock_run.call_args[0][1]
        assert args == ["get", "secret", "my-secret", "-n", "default"]
        assert mock_run.call_args[1]["output_format"] == "json"

    @patch("src.k8s_mcp.tools.get_secret_to_file.resolve")
    @patch("src.k8s_mcp.tools.get_secret_to_file.run_kubectl_checked")
    def test_relative_path_rejected_before_kubectl(self, mock_run, mock_resolve, secret_meta):
        mock_resolve.return_value = secret_meta

        result = handle_get_secret_to_file("test-context", "my-secret", "default", "relative/secret.json")

        assert result["success"] is False
        assert result["error"] == "unsafe_path"
        assert result["path"] == "relative/secret.json"
        mock_run.assert_not_called()

    @patch("src.k8s_mcp.tools.get_secret_to_file.resolve")
    @patch("src.k8s_mcp.tools.get_secret_to_file.run_kubectl_checked")
    def test_existing_file_without_overwrite_rejected(self, mock_run, mock_resolve, secret_meta, tmp_path):
        mock_resolve.return_value = secret_meta
        dst = tmp_path / "secret.json"
        dst.write_text("old content")

        result = handle_get_secret_to_file("test-context", "my-secret", "default", str(dst))

        assert result["success"] is False
        assert result["error"] == "file_exists"
        assert result["path"] == str(dst)
        mock_run.assert_not_called()
        assert dst.read_text() == "old content"

    @patch("src.k8s_mcp.tools.get_secret_to_file.resolve")
    @patch("src.k8s_mcp.tools.get_secret_to_file.run_kubectl_checked")
    def test_overwrite_true_replaces_file(self, mock_run, mock_resolve, secret_meta, tmp_path):
        mock_resolve.return_value = secret_meta
        mock_run.return_value = _secret_stdout({"username": _b64("admin")})
        dst = tmp_path / "secret.json"
        dst.write_text("old content")

        result = handle_get_secret_to_file("test-context", "my-secret", "default", str(dst), overwrite=True)

        assert result["success"] is True
        written = json.loads(dst.read_text())
        assert written["data"] == {"username": "admin"}

    @patch("src.k8s_mcp.tools.get_secret_to_file.resolve")
    @patch("src.k8s_mcp.tools.get_secret_to_file.run_kubectl_checked")
    def test_written_file_mode_is_0600(self, mock_run, mock_resolve, secret_meta, tmp_path):
        mock_resolve.return_value = secret_meta
        mock_run.return_value = _secret_stdout({"username": _b64("admin")})
        dst = tmp_path / "secret.json"

        result = handle_get_secret_to_file("test-context", "my-secret", "default", str(dst))

        assert result["success"] is True
        assert os.stat(str(dst)).st_mode & 0o777 == 0o600

    @patch("src.k8s_mcp.tools.get_secret_to_file.resolve")
    @patch("src.k8s_mcp.tools.get_secret_to_file.run_kubectl_checked")
    def test_write_failure_missing_parent_dir(self, mock_run, mock_resolve, secret_meta, tmp_path):
        mock_resolve.return_value = secret_meta
        mock_run.return_value = _secret_stdout({"username": _b64("admin")})
        dst = tmp_path / "no_such_dir" / "secret.json"

        result = handle_get_secret_to_file("test-context", "my-secret", "default", str(dst))

        assert result["success"] is False
        assert result["error"] == "file_write_failed"
        assert result["path"] == str(dst)

    @patch("src.k8s_mcp.tools.get_secret_to_file.resolve")
    @patch("src.k8s_mcp.tools.get_secret_to_file.run_kubectl_checked")
    def test_resolve_error_passthrough(self, mock_run, mock_resolve, tmp_path):
        mock_resolve.return_value = {"error": "unknown_resource", "resource": "secrets"}

        result = handle_get_secret_to_file("test-context", "my-secret", "default", str(tmp_path / "s.json"))

        assert result["success"] is False
        assert result["error"] == "unknown_resource"
        mock_run.assert_not_called()

    @patch("src.k8s_mcp.tools.get_secret_to_file.resolve")
    @patch("src.k8s_mcp.tools.get_secret_to_file.run_kubectl_checked")
    def test_validate_error_passthrough(self, mock_run, mock_resolve, tmp_path):
        mock_resolve.return_value = ResourceMeta(
            canonical="nodes", shortnames=["no"], kind="Node", group="", version="v1",
            namespaced=False, verbs=["get"],
        )

        result = handle_get_secret_to_file("test-context", "my-secret", "default", str(tmp_path / "s.json"))

        assert result["success"] is False
        assert result["error"] == "namespace_invalid"
        mock_run.assert_not_called()

    @patch("src.k8s_mcp.tools.get_secret_to_file.resolve")
    @patch("src.k8s_mcp.tools.get_secret_to_file.run_kubectl_checked")
    def test_kubectl_failure_passthrough(self, mock_run, mock_resolve, secret_meta, tmp_path):
        mock_resolve.return_value = secret_meta
        mock_run.return_value = {"error": "kubectl_failure", "command": ["kubectl"], "stderr": "NotFound"}

        result = handle_get_secret_to_file("test-context", "my-secret", "default", str(tmp_path / "s.json"))

        assert result["success"] is False
        assert result["error"] == "kubectl_failure"

    @patch("src.k8s_mcp.tools.get_secret_to_file.resolve")
    @patch("src.k8s_mcp.tools.get_secret_to_file.run_kubectl_checked")
    def test_non_utf8_value_written_base64_with_flag(self, mock_run, mock_resolve, secret_meta, tmp_path):
        binary_b64 = base64.b64encode(b"\x00\xff\xfe binary").decode("ascii")
        mock_resolve.return_value = secret_meta
        mock_run.return_value = _secret_stdout({"tls.crt": binary_b64, "username": _b64("admin")})
        dst = tmp_path / "secret.json"

        result = handle_get_secret_to_file("test-context", "my-secret", "default", str(dst))

        assert result["success"] is True
        assert result["data"]["keys"] == ["tls.crt", "username"]
        written = json.loads(dst.read_text())
        assert written["data"]["tls.crt"] == binary_b64
        assert written["data"]["username"] == "admin"
        assert written["base64_keys"] == ["tls.crt"]

    @patch("src.k8s_mcp.tools.get_secret_to_file.resolve")
    @patch("src.k8s_mcp.tools.get_secret_to_file.run_kubectl_checked")
    def test_secret_values_never_appear_in_response(self, mock_run, mock_resolve, secret_meta, tmp_path):
        plaintext = "SuperSecretValue-12345"
        mock_resolve.return_value = secret_meta
        mock_run.return_value = _secret_stdout({"password": _b64(plaintext)})
        dst = tmp_path / "secret.json"

        result = handle_get_secret_to_file("test-context", "my-secret", "default", str(dst))

        serialized = json.dumps(result)
        assert plaintext not in serialized
        assert _b64(plaintext) not in serialized
