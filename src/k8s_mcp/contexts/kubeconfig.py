"""Kubeconfig context handling (PRD §9).

No server-level --kubeconfig flag (PRD §11's rejected-alternatives entry) —
relies entirely on kubectl's own default kubeconfig resolution ($KUBECONFIG
env var, or ~/.kube/config), same as every other kubectl invocation in this
project (kubectl/runner.py never passes --kubeconfig either).

Issue 57: enumeration runs through kubectl/runner.py — the project's single
subprocess seam (SPEC §2, R11) — so its error paths are §7-shaped (codes,
`context`) and covered by the same timeout/error mapping as every other call.
"""

from __future__ import annotations

from typing import Any

from ..kubectl.runner import run_kubectl_checked


def list_kubeconfig_contexts(context: str = "default") -> list[str] | dict[str, Any]:
    """Enumerate available kubeconfig contexts.

    Uses `kubectl config get-contexts -o name` against kubectl's own default
    kubeconfig resolution. The `context` argument is nominal — this command is
    a pure local kubeconfig read, and kubectl's `config` verb ignores
    `--context` for it (verified) — it exists so the runner's error envelopes
    carry a §7-conformant `context` key.

    Returns a sorted list of context name strings, or an error dict
    (pass-through from the runner: already mapped via map_kubectl_error /
    errors.* helpers).
    """
    result = run_kubectl_checked(context, ["config", "get-contexts"], output_format="name")
    if "error" in result:
        return result

    contexts = [
        line.strip()
        for line in result["stdout"].splitlines()
        if line.strip()
    ]
    return sorted(set(contexts))
