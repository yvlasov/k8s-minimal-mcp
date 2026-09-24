"""CLI argument parsing (SPEC §4).

Flags:
  --access-level     {readonly,readwrite,admin}  default: readonly
  --allow-namespaces  comma-separated list        default: empty = all

No --kubeconfig flag — kubeconfig resolution is left entirely to kubectl's
own default behavior ($KUBECONFIG env var, or ~/.kube/config). See PRD §11's
rejected-alternatives entry for why a server-level flag was tried and dropped.
"""

from __future__ import annotations

import argparse

from .access import AccessLevel


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="k8s-mcp",
        description="Minimal verb-based Kubernetes MCP server",
    )
    parser.add_argument(
        "--access-level",
        choices=["readonly", "readwrite", "admin"],
        default="readonly",
        help="Gating level for mutating tools (default: readonly)",
    )
    parser.add_argument(
        "--allow-namespaces",
        default="",
        help="Comma-separated namespace allowlist; empty = all namespaces",
    )
    return parser.parse_args(argv)


def resolve_access_level(raw: str) -> AccessLevel:
    return AccessLevel(raw)


def resolve_allow_namespaces(raw: str) -> list[str] | None:
    """Return None when empty (allow all), else a list of namespace names."""
    if not raw or not raw.strip():
        return None
    ns = [n.strip() for n in raw.split(",") if n.strip()]
    return ns or None
