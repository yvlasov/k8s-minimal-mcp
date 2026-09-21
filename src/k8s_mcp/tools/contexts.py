"""k_list_contexts tool (PRD §6, supporting tools).

Enumerate available kubeconfig contexts.

Required: none (beyond context, which is echoed)
"""

from __future__ import annotations

from typing import Any

from ..contexts import list_kubeconfig_contexts
from ..output import envelope, envelope_list_contexts


def handle_list_contexts(
    context: str,
    kubeconfig_paths: list[str] | None = None,
) -> dict[str, Any]:
    """Handle a k_list_contexts call."""
    if kubeconfig_paths is None:
        kubeconfig_paths = []

    result = list_kubeconfig_contexts(kubeconfig_paths)
    if isinstance(result, dict) and "error" in result:
        return envelope(result, context, "k_list_contexts", success=False)

    return envelope_list_contexts(result, context)
