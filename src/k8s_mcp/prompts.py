"""Built-in MCP prompts for resource status guidance (FR11).

Prompts return a formatted string that embeds the literal tool-call shape
(exact resource= string, exact JSON field path), not a paraphrased
description — matching the project convention of exact reproduction
over narrative.

Prompts perform no cluster access themselves; they are registered
unconditionally (R7 gating governs tools that act on the cluster).
"""

from __future__ import annotations

from .utils import extract_named_entity


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


def cilium_troubleshoot_connectivity(cluster: str, issue_description: str) -> str:
    """Prompt: troubleshoot pod-to-service connectivity with Cilium.

    Returns a string instructing the model to run a step-by-step
    connectivity troubleshooting workflow using Cilium CRDs.

    The prompt supports two modes:
    - Cluster-wide triage (default): investigate fleet-wide or diffuse symptoms
      by checking ciliumnodes, ciliumclusterwidenetworkpolicies, and ciliumidentities.
    - Pod-specific narrowing: if a specific pod name appears in issue_description,
      add steps to inspect ciliumendpoints and ciliumnetworkpolicies for that pod.

    Every generated tool call includes context=<cluster> to avoid parameter-validation
    failures when the model follows the prompt's instructions verbatim.
    """
    lines = [
        f"Troubleshoot connectivity in cluster '{cluster}'.",
        f"Issue description: {issue_description}",
        "",
        "Step 1 — Check Cilium node status (are all nodes healthy?):",
        f"  k_get(resource=\"ciliumnodes\", context=\"{cluster}\", output=\"yaml\")",
        "Look for: status.conditions[] where type=\"KubeControllerReady\" or \"KubeProxyReady\" "
        "showing status=\"False\", status.state=\"disconnected\"/\"connected\" on individual nodes\n",
    ]

    lines.extend([
        "Step 2 — Check CiliumClusterwideNetworkPolicies (any cluster-wide drops?):",
        f"  k_get(resource=\"ciliumclusterwidenetworkpolicies\", context=\"{cluster}\", output=\"yaml\")",
        "Look for: spec.endpointSelector matching broad selectors (e.g. '{{}}' for all pods), "
        "ingress/egress rules with fromEndpoints/toEndpoints matchers\n",
    ])

    lines.extend([
        "Step 3 — Check CiliumIdentities (are pod identities resolved?):",
        f"  k_get(resource=\"ciliumidentities\", context=\"{cluster}\", output=\"yaml\")",
        "Look for: identities[].labels matching the pods involved in the connectivity issue, "
        "identities[].reserved keys (host, init, world, unmanaged)\n",
    ])

    # Pod-specific path: check if a pod name appears in the issue description
    pod_name = extract_named_entity(issue_description, "pod")
    if pod_name:
        lines.extend([
            "",
            f"Step 4 — Pod-specific: Check CiliumEndpoint for '{pod_name}':",
            f"  k_get(resource=\"ciliumendpoints\", name=\"{pod_name}\", context=\"{cluster}\", output=\"yaml\")",
            "Look for: status.state (Ready/NotReady), endpoint_id, connectivity.state, "
            "healthEndpoints[].healthz\n",
        ])

        lines.extend([
            "Step 5 — Pod-specific: Check CiliumNetworkPolicies affecting this pod:",
            f"  k_get(resource=\"ciliumnetworkpolicies\", context=\"{cluster}\", output=\"yaml\")",
            "Look for: spec.endpointSelector matching the pod's labels (get pod labels from "
            f"k_get(resource=\"pods\", name=\"{pod_name}\", context=\"{cluster}\", output=\"yaml\")), "
            "ingress/egress rules with fromEndpoints/toEndpoints matchers\n",
        ])

    lines.extend([
        "",
        "Note: Cilium's own eBPF drop-reason counters "
        "(cilium_drop_count_total by direction/reason) are Prometheus-exposed metrics, "
        "not reachable via any kubectl-based tool in this project. Query them directly "
        "from your Prometheus/Grafana instance or via promql:\n"
        "  sum(rate(cilium_drop_count_total{direction=\"INGRESS\",reason!=\"policy-denied\"}[5m])) by (reason)\n"
        "  sum(rate(cilium_drop_count_total{direction=\"EGRESS\"}[5m])) by (reason)",
    ])

    return "\n".join(lines)


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
