"""Issue 41: dispatch-path smoke tests for every registered tool.

Calls _dispatch() directly (not the handler) with the exact kwargs each
wrapper in server.py passes, asserting no TypeError/AttributeError from a
kwarg mismatch. This is the structural fix that prevents the entire bug
class that produced Issue 40 (two independent crashes, three commits).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.k8s_mcp.access import AccessLevel, allowed_verbs
from src.k8s_mcp.resolution.models import ResourceMeta
from src.k8s_mcp.server import _dispatch


def _pod_meta() -> ResourceMeta:
    return ResourceMeta(
        canonical="pods",
        shortnames=["po"],
        kind="Pod",
        group="",
        version="v1",
        namespaced=True,
        verbs=["get", "logs", "apply", "patch", "delete", "exec", "list"],
    )


def _secret_meta() -> ResourceMeta:
    return ResourceMeta(
        canonical="secrets",
        shortnames=["secret"],
        kind="Secret",
        group="",
        version="v1",
        namespaced=True,
        verbs=["get", "list", "apply", "patch", "delete"],
    )


def _deployment_meta() -> ResourceMeta:
    return ResourceMeta(
        canonical="deployments",
        shortnames=["deploy"],
        kind="Deployment",
        group="apps",
        version="v1",
        namespaced=True,
        verbs=["get", "list", "apply", "patch", "delete"],
    )


# Each entry: (tool_verb, handler, module_path_for_mocks, kwargs_to_pass)
# The kwargs must match exactly what the wrapper in server.py passes to _dispatch().
_TOOL_DEFINITIONS: list[tuple[str, str, dict]] = [
    (
        "list_resources",
        "src.k8s_mcp.tools.list_resources.handle_list_resources",
        {"search": None},
    ),
    (
        "get",
        "src.k8s_mcp.tools.get.handle_get",
        {
            "resource": "pods",
            "name": "my-pod",
            "namespace": "default",
            "all_namespaces": False,
            "label_selector": None,
            "field_selector": None,
            "output": None,
            "jsonpath_template": None,
            "annotation_selector": None,
        },
    ),
    (
        "get_helm_release",
        "src.k8s_mcp.tools.get_helm_release.handle_get_helm_release",
        {
            "release": "my-release",
            "namespace": "default",
            "revision": None,
            "include_manifest": False,
        },
    ),
    (
        "auth_can_i",
        "src.k8s_mcp.tools.auth_can_i.handle_auth_can_i",
        {
            "verb": "get",
            "resource": "pods",
            "name": None,
            "namespace": None,
            "as_user": None,
            "as_group": None,
            "list_all": False,
        },
    ),
    (
        "logs",
        "src.k8s_mcp.tools.logs.handle_logs",
        {
            "pod": "my-pod",
            "namespace": "default",
            "container": None,
            "tail": None,
            "previous": False,
            "since": None,
        },
    ),
    (
        "apply",
        "src.k8s_mcp.tools.apply.handle_apply",
        {
            "manifest": '{"apiVersion":"v1","kind":"Pod","metadata":{"name":"test"}}',
            "src_file": None,
            "namespace": None,
            "dry_run": "none",
            "output": None,
            "jsonpath_template": None,
        },
    ),
    (
        "patch",
        "src.k8s_mcp.tools.patch.handle_patch",
        {
            "resource": "pods",
            "name": "my-pod",
            "patch": '{"spec":{"replicas":2}}',
            "namespace": "default",
            "type": "strategic",
            "dry_run": "none",
            "output": None,
            "jsonpath_template": None,
        },
    ),
    (
        "delete",
        "src.k8s_mcp.tools.delete.handle_delete",
        {
            "resource": "pods",
            "name": "my-pod",
            "namespace": "default",
            "label_selector": None,
            "dry_run": "none",
        },
    ),
    (
        "describe",
        "src.k8s_mcp.tools.describe.handle_describe",
        {
            "resource": "pods",
            "name": "my-pod",
            "namespace": "default",
        },
    ),
    (
        "exec",
        "src.k8s_mcp.tools.exec_.handle_exec",
        {
            "pod": "my-pod",
            "command": ["ls", "-la"],
            "namespace": "default",
            "container": None,
        },
    ),
    (
        "get_secret_to_file",
        "src.k8s_mcp.tools.get_secret_to_file.handle_get_secret_to_file",
        {
            "name": "my-secret",
            "namespace": "default",
            "dst_secret_file": "/tmp/secret.yaml",
            "overwrite": False,
        },
    ),
]

# Verbs that are available at each access level (from access.py _VERB_MAP)
_ACCESS_TOOLS: dict[AccessLevel, list[str]] = {
    AccessLevel.READONLY: [
        "list_resources", "get", "auth_can_i", "logs", "describe",
    ],
    AccessLevel.READWRITE: [
        "list_resources", "get", "auth_can_i", "logs", "describe",
        "apply", "patch", "delete",
    ],
    AccessLevel.ADMIN: [
        "list_resources", "get", "get_helm_release", "auth_can_i", "logs", "describe",
        "apply", "patch", "delete", "exec", "get_secret_to_file",
    ],
}


class TestDispatchPathSmoke:
    """One parametrized smoke test per access level × tool.

    Asserts that _dispatch() can be called with the exact kwargs each wrapper
    passes, and that the handler accepts them without TypeError/AttributeError.
    """

    @pytest.mark.parametrize(
        "access_level",
        list(AccessLevel),
        ids=[level.value for level in AccessLevel],
    )
    @pytest.mark.parametrize(
        "tool_verb,handler_path,kwargs",
        _TOOL_DEFINITIONS,
        ids=[t[0] for t in _TOOL_DEFINITIONS],
    )
    def test_dispatch_no_type_error(
        self,
        access_level: AccessLevel,
        tool_verb: str,
        handler_path: str,
        kwargs: dict,
    ) -> None:
        # Skip tools not registered at this access level
        if tool_verb not in _ACCESS_TOOLS[access_level]:
            pytest.skip(f"{tool_verb} not available at {access_level.value}")

        # Import the handler
        import importlib
        module_name, func_name = handler_path.rsplit(".", 1)
        module = importlib.import_module(module_name)
        handler = getattr(module, func_name)

        # Mock the lowest-level dependencies to avoid real kubectl calls
        # Use create=True so patching works even if the attribute doesn't exist
        # in the module (e.g., list_resources doesn't import resolve)
        mock_resolve = patch.object(module, "resolve", return_value=_pod_meta(), create=True)
        mock_run_kubectl = patch.object(module, "run_kubectl", return_value={
            "stdout": "ok\n", "stderr": "", "returncode": 0,
            "command": ["kubectl", "test"],
        }, create=True)
        mock_run_kubectl_checked = patch.object(module, "run_kubectl_checked", return_value={
            "stdout": "ok\n", "stderr": "", "returncode": 0,
            "command": ["kubectl", "test"],
        }, create=True)

        with mock_resolve, mock_run_kubectl, mock_run_kubectl_checked:
            # This is the exact call shape the wrapper in server.py makes
            result = _dispatch(
                tool_verb,
                handler,
                "test-context",
                None,  # discovery_cache (None is fine — handlers accept it)
                None,  # allow_namespaces
                **kwargs,
            )

        # The call must complete without TypeError/AttributeError.
        # The result is a dict (envelope) — we don't assert on its content
        # here (that's each tool's own test file's job), only that the
        # dispatch→handler chain didn't crash on a kwarg mismatch.
        assert isinstance(result, dict)
