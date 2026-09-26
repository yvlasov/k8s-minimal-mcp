"""General-purpose text extraction utilities."""

from __future__ import annotations

import re


def extract_named_entity(text: str, entity_type: str = "pod") -> str | None:
    """Extract a named entity from free-text description.

    Searches for patterns like:
      - "pod my-pod", "pods/my-pod", "named my-pod"
      - "service my-svc", "services/my-svc"
      - "deployment my-deploy", "deployments/my-deploy"

    Entity names must match Kubernetes naming conventions:
    lowercase alphanumeric, hyphens, dots; 1-63 chars; start/end with alphanumeric.

    Args:
        text: Free-text description to search.
        entity_type: Type of entity to look for (e.g. "pod", "service", "deployment").

    Returns:
        The extracted entity name, or None if no clear match.
    """
    patterns = [
        # Case-insensitive entity type prefix, case-sensitive name
        rf'(?i:(?<![a-z0-9-]){entity_type})[s]?\s+["\']?([a-z0-9]([a-z0-9\-\.]*[a-z0-9])?)["\']?',
        rf'(?i:(?<![a-z0-9-]){entity_type})[s]?/["\']?([a-z0-9]([a-z0-9\-\.]*[a-z0-9])?)["\']?',
        # "named" pattern — case-insensitive prefix, case-sensitive name
        r'(?i:(?<![a-z0-9-])\bnamed\s+)["\']?([a-z0-9]([a-z0-9\-\.]*[a-z0-9])?)["\']?',
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            name = match.group(1)
            if 1 <= len(name) <= 63:
                return name
    return None
