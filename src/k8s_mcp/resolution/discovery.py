"""Per-context discovery cache for CRDs and extension resources (PRD R5).

Keys the cache by context name. Refreshes via `kubectl api-resources -o wide`
on miss, with TTL-based invalidation (default 5 minutes).

On-miss behavior: refresh once, then fail if still not found (avoids repeated
blocking calls).
"""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from ..kubectl.runner import run_kubectl
from ..errors import kubectl_failure, discovery_failure
from .models import ResourceMeta


@dataclass
class CacheEntry:
    """Cached discovery data for a single context."""
    resources: list[ResourceMeta]
    expires_at: float
    populated: bool = False  # True once we've successfully parsed at least one entry


# Global TTL in seconds (5 min default)
DEFAULT_TTL = 300.0


class DiscoveryCache:
    """Thread-safe per-context cache of `kubectl api-resources` output."""

    def __init__(self, ttl: float = DEFAULT_TTL) -> None:
        self._ttl = ttl
        self._entries: dict[str, CacheEntry] = {}
        self._lock = threading.Lock()

    def get(self, context: str) -> list[ResourceMeta] | None:
        """Return cached resources if valid, else None."""
        with self._lock:
            entry = self._entries.get(context)
        if entry is None:
            return None
        if time.monotonic() < entry.expires_at and entry.populated:
            return entry.resources
        return None

    def put(self, context: str, resources: list[ResourceMeta]) -> None:
        """Store a parsed discovery result."""
        entry = CacheEntry(
            resources=resources,
            expires_at=time.monotonic() + self._ttl,
            populated=True,
        )
        with self._lock:
            self._entries[context] = entry

    def invalidate(self, context: str) -> None:
        """Remove cached entry for a context."""
        with self._lock:
            self._entries.pop(context, None)

    def refresh(self, context: str) -> list[ResourceMeta] | dict[str, Any]:
        """Run kubectl api-resources and parse the result.

        Returns list[ResourceMeta] on success, or an error dict on failure.
        """
        result = run_kubectl(context, ["api-resources", "-o", "wide"])

        if result.get("error"):
            return result  # kubectl_failure dict

        raw_output = result.get("stdout", "")
        resources = _parse_api_resources(raw_output)
        if not resources:
            return discovery_failure(
                context,
                detail="kubectl api-resources returned empty output (kubectl succeeded but parser found no resources)",
            )
        self.put(context, resources)
        return resources


def _parse_api_resources(output: str) -> list[ResourceMeta]:
    """Parse `kubectl api-resources -o wide` tabular output into ResourceMeta list.

    Expected format (space/tab-aligned, header-driven column mapping):
      NAME                      SHORTNAMES   APIVERSION             NAMESPACED   KIND                      VERBS                                       CATEGORIES
      pods                      po           v1                     true         Pod                       [create delete get list patch update watch]   [basic]
      deployments               deploy       apps/v1                true         Deployment                [create delete get list patch update watch]   [basic]
      ciliumnetworkpolicies     ciliumnet    cilium.io/v2           true         CiliumNetworkPolicy       [create delete get list patch update watch]
    """
    resources: list[ResourceMeta] = []
    lines = output.strip().splitlines()
    if not lines:
        return resources

    # Find the header line (first line containing "NAME" as a column)
    header_line = None
    data_start = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        # Check if this is a separator line
        if stripped.startswith("───") or stripped.startswith("---"):
            data_start = i + 1
            continue
        # Check if this looks like a header line
        upper = stripped.upper()
        if "NAME" in upper and ("APIVERSION" in upper or "VERSIONS" in upper):
            header_line = stripped
            data_start = i + 1
            break

    if header_line is None:
        return resources

    # Regex pattern for data lines:
    # NAME SHORTNAMES APIVERSION NAMESPACED KIND VERBS [CATEGORIES]
    # SHORTNAMES may be empty (adjacent whitespace)
    # APIVERSION may contain / (group/version) or be just version (e.g., v1)
    # NAMESPACED is true/false
    # KIND is a word
    # VERBS is a comma-separated list (no brackets in kubectl -o wide output)
    # CATEGORIES is optional, also comma-separated (no brackets)
    pattern = re.compile(
        r'^(\S+)'                          # NAME
        r'\s+(\S*)'                        # SHORTNAMES (may be empty)
        r'\s+(\S+)'                        # APIVERSION (may contain /)
        r'\s+(true|false)'                 # NAMESPACED
        r'\s+(\S+)'                        # KIND
        r'\s+(\S+)'                        # VERBS (comma-separated, no brackets)
        r'(?:\s+(\S+))?'                   # CATEGORIES (optional, comma-separated)
        r'\s*$'
    )

    for line in lines[data_start:]:
        stripped = line.strip()
        if not stripped:
            continue

        match = pattern.match(stripped)
        if not match:
            continue

        name = match.group(1)
        shortnames_str = match.group(2)
        apiversion = match.group(3)
        namespaced_str = match.group(4)
        kind = match.group(5)
        verbs_str = match.group(6)
        # categories = match.group(7)  # Not used currently

        # Skip aggregated/cluster-admin-only resources
        if name in ("componentstatuses", "cs", "nodes/metrics", "nodes/proxy"):
            continue

        # Parse APIVERSION to extract group and version
        group = ""
        version = "v1"
        if apiversion:
            if "/" in apiversion:
                group, _, version = apiversion.partition("/")
            else:
                version = apiversion

        # Parse VERBS (comma-separated in kubectl -o wide output)
        if verbs_str:
            verbs = [v.strip() for v in verbs_str.split(",") if v.strip()]
        else:
            verbs = ["get", "apply", "patch", "delete"]

        shortnames = [s.strip() for s in shortnames_str.split(",") if s.strip()] if shortnames_str else []
        namespaced = namespaced_str.lower() in ("true", "yes", "1")

        resources.append(ResourceMeta(
            canonical=name,
            shortnames=shortnames,
            kind=kind,
            group=group,
            version=version,
            namespaced=namespaced,
            verbs=verbs,
        ))

    return resources
