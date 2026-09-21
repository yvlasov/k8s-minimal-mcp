"""Resource name → GVK resolver (PRD R2, R6, R8).

Two-tier lookup:
  1. Core table (hardcoded, static) — wins ties
  2. Per-context discovery cache (dynamic, TTL-cached)

Ambiguous matches never auto-resolve — return all candidates (R6).
Pre-execution validation (R8) checks namespaced/cluster-scoped and verb
support before kubectl is invoked.
"""

from __future__ import annotations

import difflib
from typing import Any, cast

from .core_table import load_core_table
from .discovery import DiscoveryCache
from .models import ResourceMeta
from ..errors import (
    ambiguous_resource,
    unknown_resource,
    verb_unsupported,
    namespace_invalid,
)

# Lazy-loaded core table
_core_table: list[ResourceMeta] | None = None


def _get_core_table() -> list[ResourceMeta]:
    global _core_table
    if _core_table is None:
        _core_table = load_core_table()
    return _core_table


def resolve(
    context: str,
    resource: str,
    *,
    discovery_cache: DiscoveryCache | None = None,
    core_table: list[ResourceMeta] | None = None,
) -> ResourceMeta | dict[str, Any]:
    """Resolve a resource name to a ResourceMeta.

    Args:
        context: kubeconfig context name.
        resource: shortname, plural, kind, or fully-qualified name.
        discovery_cache: optional per-context cache (None = no cache lookup).
        core_table: optional pre-loaded core table (None = load default).

    Returns:
        ResourceMeta on success, or an error dict on failure.
    """
    table = core_table or _get_core_table()

    # Tier 1: Core table lookup
    core_matches = [r for r in table if r.matches(resource)]
    if core_matches:
        if len(core_matches) == 1:
            return core_matches[0]
        # Multiple core matches — ambiguous (e.g. "policy" could be PodDisruptionPolicy or Policy)
        return ambiguous_resource(
            context,
            [m.fully_qualified_name for m in core_matches],
            hint="specify resource as <name>.<group>",
        )

    # Tier 2: Discovery cache (CRDs and extensions)
    if discovery_cache:
        cached = discovery_cache.get(context)
        if cached is None:
            refresh_result = discovery_cache.refresh(context)
            if isinstance(refresh_result, dict) and "error" in refresh_result:
                return refresh_result
            cached = cast(list[ResourceMeta], refresh_result)
        # cached is now list[ResourceMeta] | None
        if cached is not None:
            matches = [r for r in cached if r.matches(resource)]
            if matches:
                if len(matches) == 1:
                    return matches[0]
                return ambiguous_resource(
                    context,
                    [m.fully_qualified_name for m in matches],
                    hint="specify resource as <name>.<group>",
                )

    # No match — fuzzy suggestions
    candidate_pool = table
    if discovery_cache:
        cached = discovery_cache.get(context) or []
        candidate_pool = table + cached
    suggestions = _fuzzy_suggest(resource, candidate_pool)

    return unknown_resource(context, resource, suggestions=suggestions[:5])


def validate(
    resource_meta: ResourceMeta,
    verb: str,
    namespace: str | None,
    *,
    all_namespaces: bool = False,
) -> dict[str, Any] | None:
    """Pre-execution validation (PRD R8).

    Checks:
      - Verb support: is this verb in the resource's verb list?
      - Namespace scope: cluster-scoped resources must not have a namespace.

    Returns None on success, or an error dict on failure.
    """
    # Verb check
    if verb not in resource_meta.verbs:
        return verb_unsupported(
            context="__unknown__",  # filled by caller
            resource=resource_meta.canonical,
            verb=verb,
        )

    # Namespace scope check
    if resource_meta.namespaced and namespace is None and not all_namespaces:
        return namespace_invalid(
            context="__unknown__",
            resource=resource_meta.canonical,
            detail=f"{resource_meta.kind} is namespaced; provide a namespace",
        )
    if not resource_meta.namespaced and namespace is not None:
        return namespace_invalid(
            context="__unknown__",
            resource=resource_meta.canonical,
            detail=f"{resource_meta.kind} is cluster-scoped; do not provide a namespace",
        )

    return None


def _fuzzy_suggest(query: str, candidates: list[ResourceMeta], limit: int = 5) -> list[str]:
    """Return up to `limit` candidate canonical names, sorted by similarity."""
    names = [c.canonical for c in candidates]
    close = difflib.get_close_matches(query, names, n=limit, cutoff=0.5)
    return close or names[:limit]
