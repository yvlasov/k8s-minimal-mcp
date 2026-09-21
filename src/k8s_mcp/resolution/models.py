"""ResourceMeta model for core table and discovery cache entries.

Both sources (core_resources.toml and kubectl api-resources) populate this
same shape, enabling unified lookup logic in resolver.py.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ResourceMeta(BaseModel):
    """Metadata for a single Kubernetes resource type."""

    canonical: str          # plural lowercase, e.g. "pods", "deployments"
    shortnames: list[str]   # e.g. ["po"], ["deploy"], []
    kind: str               # e.g. "Pod", "Deployment"
    group: str              # "" for core, "apps", "networking.k8s.io", etc.
    version: str            # e.g. "v1"
    namespaced: bool
    verbs: list[str]        # subset of {get, logs, apply, patch, delete, exec}

    @property
    def api_version(self) -> str:
        if self.group:
            return f"{self.group}/{self.version}"
        return self.version

    @property
    def fully_qualified_name(self) -> str:
        """Canonical name for group-scoped lookup, e.g. 'networkpolicies.networking.k8s.io'."""
        if self.group:
            return f"{self.canonical}.{self.group}"
        return self.canonical

    def matches(self, query: str) -> bool:
        """Check if query matches this resource by any of its identifiers."""
        q = query.lower().strip()
        if not q:
            return False
        return (
            q == self.canonical
            or q == self.kind.lower()
            or q in self.shortnames
            or q == self.fully_qualified_name
        )
