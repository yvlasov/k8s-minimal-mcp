"""Response envelope (PRD R3).

Wraps every tool response with:
  - context: echoed back from input
  - tool: the tool name that produced the response
  - (optional) _bound: reduction metadata from R4

Ensures every result is self-identifying in interleaved cross-context sessions.
"""

from __future__ import annotations

from typing import Any


def envelope(
    response: Any,
    context: str,
    tool: str,
    *,
    success: bool = True,
) -> dict[str, Any]:
    """Wrap a tool response in the standard envelope.

    Args:
        response: the tool's actual output (pruned, bounded).
        context: the kubeconfig context used.
        tool: the MCP tool name (e.g. "k_get").
        success: False if this is an error response.

    Returns:
        Enveloped dict ready for MCP transport.
    """
    out: dict[str, Any] = {
        "context": context,
        "tool": tool,
        "success": success,
    }

    if success:
        out["data"] = response
    else:
        # Error responses: merge error dict directly (it already has context/error keys)
        if isinstance(response, dict):
            out.update(response)
        else:
            out["error"] = str(response)

    return out


def envelope_list_contexts(
    contexts: list[str],
    context: str,
) -> dict[str, Any]:
    """Special envelope for k_list_contexts (no single context used)."""
    return {
        "context": context,
        "tool": "k_list_contexts",
        "success": True,
        "data": {
            "contexts": contexts,
            "count": len(contexts),
        },
    }
