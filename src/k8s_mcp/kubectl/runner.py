"""kubectl subprocess runner (PRD R11).

Single entry point for all kubectl invocations. Captures stdout/stderr,
enforces timeout, returns structured result.

Every tool goes through this — never call subprocess directly.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Any

from .errors import map_kubectl_error


@dataclass
class KubectlResult:
    """Structured result from a kubectl subprocess call."""
    stdout: str
    stderr: str
    returncode: int
    command: list[str]


def run_kubectl(
    context: str,
    args: list[str],
    *,
    timeout: float = 30.0,
    stdin: str | None = None,
    output_format: str | None = "json",
) -> dict[str, Any]:
    """Execute kubectl with the given context and arguments.

    Args:
        context: kubeconfig context name.
        args: kubectl subcommand and flags (without --context, -o).
        timeout: subprocess timeout in seconds.
        stdin: optional stdin content (for apply/patch with manifest data).
        output_format: output format flag value (None to omit -o flag entirely).

    Returns:
        dict with keys: stdout, stderr, returncode, command
        On exception: dict with key "error" containing an error description.
    """
    base_args = [
        "kubectl",
        "--context", context,
    ]
    if output_format is not None:
        base_args.extend(["-o", output_format])
    base_args += args

    try:
        proc = subprocess.run(
            base_args,
            input=stdin,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return KubectlResult(
            stdout=proc.stdout,
            stderr=proc.stderr,
            returncode=proc.returncode,
            command=base_args,
        ).__dict__
    except subprocess.TimeoutExpired:
        return {"error": f"kubectl timed out after {timeout}s", "command": base_args}
    except FileNotFoundError:
        return {"error": "kubectl binary not found in PATH"}
    except OSError as e:
        return {"error": f"oserror running kubectl: {e}", "command": base_args}


def run_kubectl_checked(
    context: str,
    args: list[str],
    *,
    timeout: float = 30.0,
    stdin: str | None = None,
    output_format: str | None = "json",
) -> dict[str, Any]:
    """Execute kubectl and map non-zero exit codes to structured errors.

    Wraps run_kubectl — if the process exits non-zero with no Python-level
    exception, calls map_kubectl_error() to produce a proper {"error": ...} dict.

    Args:
        context: kubeconfig context name.
        args: kubectl subcommand and flags.
        timeout: subprocess timeout in seconds.
        stdin: optional stdin content.
        output_format: output format flag value (None to omit -o flag).

    Returns:
        dict with keys: stdout, stderr, returncode, command on success
        dict with key "error" on exception or non-zero kubectl exit.
    """
    result = run_kubectl(context, args, timeout=timeout, stdin=stdin, output_format=output_format)

    # Python-level exception already returned an "error" dict
    if "error" in result:
        return result

    # Non-zero exit code → map to structured error
    if result.get("returncode", 0) != 0:
        return map_kubectl_error(
            context=context,
            command=result.get("command", args),
            stderr=result.get("stderr", ""),
            returncode=result["returncode"],
        )

    return result
