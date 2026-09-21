"""k_list_resources tool (PRD §15 FR3).

List available Kubernetes resource types from the discovery cache.

Required: context
Optional: search (case-insensitive substring filter)
"""

from __future__ import annotations

from typing import Any

from ..resolution.discovery import DiscoveryCache
from ..output import envelope


def _filter_resources(
    resources: list,
    search: str | None,
) -> list:
    """Filter resources by case-insensitive substring match against canonical, kind, and group."""
    if not search:
        return resources

    search_lower = search.lower()
    return [
        r for r in resources
        if (
            search_lower in r.canonical.lower()
            or search_lower in r.kind.lower()
            or search_lower in r.group.lower()
        )
    ]


def _serialize_resource(r) -> dict[str, Any]:
    """Serialize a ResourceMeta to a plain dict."""
    return {
        "name": r.canonical,
        "shortnames": r.shortnames,
        "kind": r.kind,
        "api_version": r.api_version,
        "namespaced": r.namespaced,
        "verbs": r.verbs,
    }


def handle_list_resources(
    context: str,
    *,
    search: str | None = None,
    discovery_cache: DiscoveryCache | None = None,
) -> dict[str, Any]:
    """Handle a k_list_resources call."""
    if discovery_cache is None:
        return envelope({
            "resources": [],
            "count": 0,
        }, context, "k_list_resources", success=True)

    resources = discovery_cache.get(context)
    if resources is None:
        result = discovery_cache.refresh(context)
        if isinstance(result, dict) and "error" in result:
            return envelope(result, context, "k_list_resources", success=False)
        resources = result

    filtered = _filter_resources(resources, search)

    return envelope({
        "resources": [_serialize_resource(r) for r in filtered],
        "count": len(filtered),
    }, context, "k_list_resources", success=True)
