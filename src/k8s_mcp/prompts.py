"""Built-in MCP prompts for resource status guidance (FR11).

Prompts return a formatted string that embeds the literal tool-call shape
(exact resource= string, exact JSON field path), not a paraphrased
description — matching the project convention of exact reproduction
over narrative.

Prompts perform no cluster access themselves; they are registered
unconditionally (R7 gating governs tools that act on the cluster).
"""

from __future__ import annotations


def argocd_app_health(name: str, namespace: str) -> str:
    """Prompt: check ArgoCD Application sync/health status.

    Returns a string instructing the model to call k_get for an ArgoCD
    Application and read specific status fields.
    """
    return (
        f"Check the sync and health status of the ArgoCD Application '{name}' "
        f"in namespace '{namespace}'.\n\n"
        "Run:\n"
        f"  k_get(resource=\"applications.argoproj.io\", name=\"{name}\", "
        f"namespace=\"{namespace}\", output=\"yaml\")\n\n"
        "Then read these fields from the response:\n"
        "  - .status.sync.status — one of: Synced, OutOfSync, Unknown\n"
        "  - .status.health.status — one of: Healthy, Unhealthy, Missing, Unknown\n"
        "  - .status.resources[] — list of individual resource health entries\n"
        "    (each has group, kind, namespace, name, status, health.status)\n\n"
        "Note: the hierarchical resource tree, live git-vs-cluster diffs, "
        "and custom resource actions are NOT reachable via k_get — they are "
        "only available through the ArgoCD API server (not the Kubernetes API)."
    )


def cilium_troubleshoot_connectivity(namespace: str, pod: str) -> str:
    """Prompt: troubleshoot pod-to-service connectivity with Cilium.

    Returns a string instructing the model to run a step-by-step
    connectivity troubleshooting workflow using Cilium CRDs.
    """
    return (
        f"Troubleshoot connectivity for pod '{pod}' in namespace '{namespace}'.\n\n"
        "Step 1 — Check CiliumEndpoint (is the pod managed by Cilium?):\n"
        f"  k_get(resource=\"ciliumendpoints\", name=\"{pod}\", "
        f"namespace=\"{namespace}\", output=\"yaml\")\n"
        "Look for: status.state (Ready/NotReady), endpoint_id, connectivity\n\n"
        "Step 2 — Check CiliumNetworkPolicy (any policies affecting this pod?):\n"
        f"  k_get(resource=\"ciliumnetworkpolicies\", namespace=\"{namespace}\", "
        f"output=\"yaml\")\n"
        "Look for: spec.endpointSelector matching the pod's labels, ingress/egress rules\n\n"
        "Step 3 — Describe the pod for network-related annotations:\n"
        f"  k_describe(resource=\"pods\", name=\"{pod}\", namespace=\"{namespace}\")\n"
        "Look for: ciliumEndpointReady annotation, network policies referenced\n\n"
        "Note: Hubble flow and drop-verdict data are NOT reachable via any tool "
        "in this project — there is no backing API resource for Hubble."
    )


def rbac_effective_permissions(as_user: str, namespace: str) -> str:
    """Prompt: check effective RBAC permissions for a user.

    Returns a string instructing the model to use k_auth_can_i (FR13)
    to check permissions. Until FR13 ships, states the gap explicitly.
    """
    return (
        f"Check effective RBAC permissions for user '{as_user}' in namespace "
        f"'{namespace}'.\n\n"
        "Once FR13 (k_auth_can_i) ships, run:\n"
        f"  k_auth_can_i(verb=\"get\", resource=\"pods\", namespace=\"{namespace}\", "
        f"as_user=\"{as_user}\")\n"
        "Repeat for other verbs and resources you need to verify.\n\n"
        "Until FR13 ships, there is no tool for effective-permission checks. "
        "The alternative — manually cross-referencing Roles, ClusterRoles, "
        "RoleBindings, and ClusterRoleBindings — is error-prone and not "
        "recommended."
    )
