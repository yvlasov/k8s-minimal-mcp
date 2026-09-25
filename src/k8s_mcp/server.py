"""Server entrypoint (SPEC §4).

Startup sequence:
  1. Parse CLI args (--access-level, --allow-namespaces)
  2. Load core resource table
  3. Enumerate kubeconfig contexts (kubectl's own default resolution — no --kubeconfig flag)
  4. Compute allowed verb set from access level
  5. Register only tools whose verb is in the allowed set (R7)
  6. Start FastMCP server

Namespace allowlist is enforced per-call in tools, not at registration.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

from fastmcp import FastMCP

from .access import AccessLevel, allowed_verbs, tool_for_verb
from .cli import parse_args, resolve_access_level, resolve_allow_namespaces
from .resolution import DiscoveryCache
from .tools import (
    handle_get,
    handle_logs,
    handle_apply,
    handle_patch,
    handle_delete,
    handle_exec,
    handle_list_contexts,
    handle_describe,
    handle_list_resources,
    handle_get_secret_to_file,
)

logger = logging.getLogger("k8s_mcp")

# Open-question flags (PRD §13)
_SHIP_DESCRIBE = True  # TBD — ship k_describe for now
_SHIP_EXEC = True      # TBD — ship k_exec at admin for now


def _dispatch(
    verb: str,
    handler,
    context: str,
    discovery_cache: DiscoveryCache,
    allow_namespaces: list[str] | None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Shared dispatch logic: namespace allowlist, audit log, discovery_cache injection."""
    # Namespace allowlist check (orthogonal gating axis)
    ns = kwargs.get("namespace")
    if allow_namespaces and ns and ns not in allow_namespaces:
        from .errors import namespace_invalid
        resource_name = kwargs.get("resource", kwargs.get("pod", "<unknown>"))
        err = namespace_invalid(context, resource_name,
                                detail=f"namespace '{ns}' not in allowlist")
        err["context"] = context
        from .output import envelope
        return envelope(err, context, f"k_{verb}", success=False)

    # Audit log for mutating calls
    if verb in ("apply", "patch", "delete", "exec"):
        resource_name = kwargs.get("name", kwargs.get("resource", kwargs.get("pod", "?")))
        logger.info("MUTATE: context=%s verb=%s %s", context, verb, resource_name)

    # Pass discovery_cache to handler
    kwargs["discovery_cache"] = discovery_cache
    return handler(context, **kwargs)


def main(argv: list[str] | None = None) -> None:
    """Entry point for the k8s-mcp server."""
    args = parse_args(argv)
    access_level = resolve_access_level(args.access_level)
    allow_namespaces = resolve_allow_namespaces(args.allow_namespaces)

    # Configure logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logger.info("Starting k8s-mcp server (access_level=%s)", access_level.value)

    # Discovery cache (R5)
    discovery_cache = DiscoveryCache()

    # Build FastMCP app
    app = FastMCP(
        name="k8s-minimal-mcp",
        instructions="Minimal verb-based Kubernetes MCP server. All operations require a 'context' parameter.",
    )

    # Register k_list_contexts (always available)
    @app.tool(name="k_list_contexts")
    def list_contexts(context: str = "default") -> dict[str, Any]:
        return handle_list_contexts(context)

    # Register verb-based tools filtered by access level (R7)
    allowed = allowed_verbs(access_level)

    if "list_resources" in allowed:
        @app.tool(name="k_list_resources", description="k_list_resources: search: Optional case-insensitive substring filter against resource name, kind, and group")
        def list_resources(context: str, search: str | None = None) -> dict[str, Any]:
            return _dispatch("list_resources", handle_list_resources, context, discovery_cache, allow_namespaces,
                             search=search)

    if "get" in allowed:
        @app.tool(name="k_get", description="k_get: resource: Resource type; name: Resource name; namespace: Namespace; all_namespaces: List across all namespaces; label_selector: Kubernetes label selector; field_selector: Kubernetes field selector; output: Output format (name/json/yaml/wide/jsonpath); jsonpath_template: JsonPath template for output=jsonpath (for multiple fields use {.items[*]['field1','field2']} or {range}...{end} — nested {...} groups are not supported); annotation_selector: Filter by annotations (key=value, key!=value, key)")
        def get(context: str, resource: str, name: str | None = None, namespace: str | None = None,
                all_namespaces: bool = False, label_selector: str | None = None,
                field_selector: str | None = None, output: str | None = None,
                jsonpath_template: str | None = None, annotation_selector: str | None = None) -> dict[str, Any]:
            return _dispatch("get", handle_get, context, discovery_cache, allow_namespaces,
                             resource=resource, name=name, namespace=namespace,
                             all_namespaces=all_namespaces, label_selector=label_selector,
                             field_selector=field_selector, output=output,
                             jsonpath_template=jsonpath_template, annotation_selector=annotation_selector)

    if "logs" in allowed:
        @app.tool(name="k_logs", description="k_logs: pod: Pod name; namespace: Pod namespace; container: Container name; tail: Number of lines from the end; previous: Use previous container instance; since: Return logs newer than a relative duration")
        def logs(context: str, pod: str, namespace: str | None = None,
                 container: str | None = None, tail: int | None = None,
                 previous: bool = False, since: str | None = None) -> dict[str, Any]:
            return _dispatch("logs", handle_logs, context, discovery_cache, allow_namespaces,
                             pod=pod, namespace=namespace, container=container,
                             tail=tail, previous=previous, since=since)

    if "apply" in allowed:
        @app.tool(name="k_apply", description="k_apply: manifest: JSON/YAML manifest to apply (exactly one of manifest or src_file is required); src_file: absolute path to a file containing the manifest; namespace: Namespace for namespaced resources; dry_run: Dry-run mode; output: Output format (json/yaml/jsonpath); jsonpath_template: JsonPath template for output=jsonpath (for multiple fields use {.items[*]['field1','field2']} or {range}...{end} — nested {...} groups are not supported)")
        def apply(context: str, manifest: str | None = None, src_file: str | None = None, namespace: str | None = None,
                  dry_run: str = "none", output: str | None = None,
                  jsonpath_template: str | None = None) -> dict[str, Any]:
            return _dispatch("apply", handle_apply, context, discovery_cache, allow_namespaces,
                             manifest=manifest, src_file=src_file, namespace=namespace, dry_run=dry_run,
                             output=output, jsonpath_template=jsonpath_template)

    if "patch" in allowed:
        @app.tool(name="k_patch", description="k_patch: resource: Resource type; name: Resource name to patch; patch: JSON patch document; namespace: Namespace; type: Patch type; dry_run: Dry-run mode; output: Output format (json/yaml/jsonpath); jsonpath_template: JsonPath template for output=jsonpath (for multiple fields use {.items[*]['field1','field2']} or {range}...{end} — nested {...} groups are not supported)")
        def patch(context: str, resource: str, name: str, patch: str,
                  namespace: str | None = None, type: str = "strategic",  # noqa: A002
                  dry_run: str = "none", output: str | None = None,
                  jsonpath_template: str | None = None) -> dict[str, Any]:
            return _dispatch("patch", handle_patch, context, discovery_cache, allow_namespaces,
                             resource=resource, name=name, patch=patch,
                             namespace=namespace, type=type, dry_run=dry_run,
                             output=output, jsonpath_template=jsonpath_template)

    if "delete" in allowed:
        @app.tool(name="k_delete", description="k_delete: resource: Resource type; name: Resource name; namespace: Namespace; label_selector: Delete all resources matching this label selector; dry_run: Dry-run mode")
        def delete(context: str, resource: str, name: str | None = None,
                   namespace: str | None = None, label_selector: str | None = None,
                   dry_run: str = "none") -> dict[str, Any]:
            return _dispatch("delete", handle_delete, context, discovery_cache, allow_namespaces,
                             resource=resource, name=name, namespace=namespace,
                             label_selector=label_selector, dry_run=dry_run)

    # Conditional: k_describe (PRD §13 open)
    if _SHIP_DESCRIBE and "describe" in allowed:
        @app.tool(name="k_describe", description="k_describe: resource: Resource type; name: Resource name; namespace: Namespace")
        def describe(context: str, resource: str, name: str,
                     namespace: str | None = None) -> dict[str, Any]:
            return _dispatch("describe", handle_describe, context, discovery_cache, allow_namespaces,
                             resource=resource, name=name, namespace=namespace)

    # Conditional: k_exec (admin only, PRD §13 open)
    if _SHIP_EXEC and access_level == AccessLevel.ADMIN:
        @app.tool(name="k_exec", description="k_exec: pod: Pod name; command: Command to execute; namespace: Pod namespace; container: Container name")
        def exec_cmd(context: str, pod: str, command: list[str],
                     namespace: str | None = None, container: str | None = None) -> dict[str, Any]:
            return _dispatch("exec", handle_exec, context, discovery_cache, allow_namespaces,
                             pod=pod, command=command, namespace=namespace, container=container)

    # k_get_secret_to_file (admin only, PRD §15 FR9 — named R1 exception)
    if "get_secret_to_file" in allowed:
        @app.tool(name="k_get_secret_to_file", description="k_get_secret_to_file: name: Secret name; namespace: Secret namespace; dst_secret_file: Absolute path on the server's filesystem to write the decoded Secret to; overwrite: Overwrite the destination file if it already exists. Secret values are written only to the file and never appear in the response — only key names and the destination path are returned")
        def get_secret_to_file(context: str, name: str, namespace: str,
                               dst_secret_file: str, overwrite: bool = False) -> dict[str, Any]:
            return _dispatch("get_secret_to_file", handle_get_secret_to_file, context, discovery_cache, allow_namespaces,
                             name=name, namespace=namespace, dst_secret_file=dst_secret_file,
                             overwrite=overwrite)

    logger.info("Registered tools for access level %s", access_level.value)

    # Register prompts (unconditional — prompts perform no cluster access)
    from .prompts import argocd_app_health, cilium_troubleshoot_connectivity, rbac_effective_permissions

    @app.prompt(name="argocd_app_health", description="Check ArgoCD Application sync and health status")
    def prompt_argocd_app_health(name: str, namespace: str) -> str:
        return argocd_app_health(name, namespace)

    @app.prompt(name="cilium_troubleshoot_connectivity", description="Troubleshoot pod-to-service connectivity with Cilium")
    def prompt_cilium_troubleshoot_connectivity(namespace: str, pod: str) -> str:
        return cilium_troubleshoot_connectivity(namespace, pod)

    @app.prompt(name="rbac_effective_permissions", description="Check effective RBAC permissions for a user")
    def prompt_rbac_effective_permissions(as_user: str, namespace: str) -> str:
        return rbac_effective_permissions(as_user, namespace)

    logger.info("Running FastMCP server...")
    app.run()


if __name__ == "__main__":
    main()
