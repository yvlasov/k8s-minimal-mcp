"""Issue 41: dispatch-path smoke tests for every registered tool.

Calls _dispatch() directly (not the handler) with the exact kwargs each
wrapper in server.py passes, asserting no TypeError/AttributeError from a
kwarg mismatch. This is the structural fix that prevents the entire bug
class that produced Issue 40 (two independent crashes, three commits).
"""

from __future__ import annotations

import importlib
from contextlib import ExitStack
from typing import Any
from unittest.mock import patch

import pytest

from src.k8s_mcp.access import AccessLevel
from src.k8s_mcp.resolution.models import ResourceMeta
from src.k8s_mcp.server import _dispatch, register_tools


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
            "jsonpath": None,
            "annotation_selector": None,
            "grep": None,
            "grep_ignore_case": False,
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
            "since_time": None,
            "limit_bytes": None,
            "grep": None,
            "grep_ignore_case": False,
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
            "jsonpath": None,
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
            "jsonpath": None,
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
            "grep": None,
            "grep_ignore_case": False,
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


class _RecordingApp:
    """Minimal fake of the FastMCP surface `register_tools` uses (Issue 56).

    Records the function object each `@app.tool(name=...)`/`@app.prompt(name=...)`
    decorator receives, so tests can drive the registered wrappers without
    starting the stdio loop.
    """

    def __init__(self) -> None:
        self.tools: dict[str, Any] = {}
        self.prompts: dict[str, Any] = {}

    def tool(self, name: str, description: str | None = None):
        def decorator(fn):
            self.tools[name] = fn
            return fn

        return decorator

    def prompt(self, name: str, description: str | None = None):
        def decorator(fn):
            self.prompts[name] = fn
            return fn

        return decorator


# The exact registration surface per access level (PRD §12: 6/9/12).
_EXPECTED_TOOLS: dict[AccessLevel, set[str]] = {
    AccessLevel.READONLY: {
        "k_list_contexts", "k_list_resources", "k_get", "k_auth_can_i", "k_logs", "k_describe",
    },
    AccessLevel.READWRITE: {
        "k_list_contexts", "k_list_resources", "k_get", "k_auth_can_i", "k_logs", "k_describe",
        "k_apply", "k_patch", "k_delete",
    },
    AccessLevel.ADMIN: {
        "k_list_contexts", "k_list_resources", "k_get", "k_auth_can_i", "k_logs", "k_describe",
        "k_apply", "k_patch", "k_delete", "k_get_helm_release", "k_exec", "k_get_secret_to_file",
    },
}

_PROMPT_KWARGS: dict[str, dict] = {
    "argocd_app_health": {"name": "my-app", "namespace": "argocd"},
    "cilium_troubleshoot_connectivity": {"cluster": "main", "issue_description": "cannot reach service"},
    "rbac_effective_permissions": {"as_user": "alice", "namespace": "default"},
}

# registered tool name -> (handler module path, kwargs matching the wrapper signature)
_WRAPPER_TARGETS: dict[str, tuple[str, dict]] = {
    f"k_{verb}": (path, kwargs) for verb, path, kwargs in _TOOL_DEFINITIONS
}
_WRAPPER_TARGETS["k_list_contexts"] = ("src.k8s_mcp.tools.contexts.handle_list_contexts", {})


class TestRegistrationPerAccessLevel:
    """Issue 56: the registration surface itself (R7, SPEC §4 step 5) is now testable."""

    @pytest.mark.parametrize(
        "access_level", list(AccessLevel), ids=[level.value for level in AccessLevel]
    )
    def test_exact_tool_set(self, access_level: AccessLevel) -> None:
        fake = _RecordingApp()
        register_tools(fake, access_level, None, None)
        assert set(fake.tools) == _EXPECTED_TOOLS[access_level]

    @pytest.mark.parametrize(
        "access_level", list(AccessLevel), ids=[level.value for level in AccessLevel]
    )
    def test_prompts_registered_unconditionally(self, access_level: AccessLevel) -> None:
        fake = _RecordingApp()
        register_tools(fake, access_level, None, None)
        assert set(fake.prompts) == set(_PROMPT_KWARGS)
        for name, kwargs in _PROMPT_KWARGS.items():
            text = fake.prompts[name](**kwargs)
            assert isinstance(text, str) and text, name


class TestRegisteredWrapperDriveThrough:
    """Issue 56 / DoD item 1: every registered `@app.tool` wrapper, driven as an MCP
    client would, reaches `_dispatch()` → handler without TypeError.

    Complements `test_dispatch_no_type_error` (which calls `_dispatch()` directly):
    this exercises each wrapper's own signature → `_dispatch()` kwargs mapping —
    the seam that the wrappers being nested inside `main()` made untestable
    (the Issue 40 bug class).
    """

    @pytest.mark.parametrize(
        "access_level", list(AccessLevel), ids=[level.value for level in AccessLevel]
    )
    def test_every_registered_wrapper_reaches_handler(self, access_level: AccessLevel) -> None:
        fake = _RecordingApp()
        register_tools(fake, access_level, None, None)

        for tool_name, wrapper in fake.tools.items():
            module_path, kwargs = _WRAPPER_TARGETS[tool_name]
            module = importlib.import_module(module_path.rsplit(".", 1)[0])
            ok_result = {
                "stdout": "ok\n", "stderr": "", "returncode": 0,
                "command": ["kubectl", "test"],
            }
            with ExitStack() as stack:
                stack.enter_context(patch.object(
                    module, "resolve", return_value=_pod_meta(), create=True))
                stack.enter_context(patch.object(
                    module, "run_kubectl", return_value=ok_result, create=True))
                stack.enter_context(patch.object(
                    module, "run_kubectl_checked", return_value=ok_result, create=True))
                stack.enter_context(patch.object(
                    module, "list_kubeconfig_contexts", return_value=["ctx-a"], create=True))
                result = wrapper("test-context", **kwargs)

            assert isinstance(result, dict), tool_name
            assert {"context", "tool", "success"} <= set(result), tool_name
            assert result["tool"] == tool_name, tool_name
            assert result["context"] == "test-context", tool_name
