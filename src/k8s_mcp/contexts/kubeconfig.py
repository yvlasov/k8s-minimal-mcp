"""Kubeconfig context handling (PRD §9).

No server-level --kubeconfig flag (PRD §11's rejected-alternatives entry) —
relies entirely on kubectl's own default kubeconfig resolution ($KUBECONFIG
env var, or ~/.kube/config), same as every other kubectl invocation in this
project (kubectl/runner.py never passes --kubeconfig either).
"""

from __future__ import annotations

import subprocess
from typing import Any


def list_kubeconfig_contexts() -> list[str] | dict[str, Any]:
    """Enumerate available kubeconfig contexts.

    Uses `kubectl config get-contexts -o name` against kubectl's own default
    kubeconfig resolution. Returns a sorted list of context name strings, or
    an error dict.
    """
    args = ["kubectl", "config", "get-contexts", "-o", "name"]
    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if proc.returncode != 0:
            return {"error": "kubectl_failure", "stderr": proc.stderr, "exit_code": proc.returncode}
        contexts = [
            line.strip()
            for line in proc.stdout.strip().splitlines()
            if line.strip() and not line.startswith("CONTEXT")
        ]
        return sorted(set(contexts))
    except subprocess.TimeoutExpired:
        return {"error": "kubectl timed out listing contexts"}
    except (FileNotFoundError, OSError) as e:
        return {"error": f"failed to run kubectl: {e}"}
