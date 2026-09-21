"""kubectl stderr → internal error codes mapping (PRD §7).

Maps common kubectl failure patterns to our structured error contract.
Called by tools after a non-zero returncode from runner.py.
"""

from __future__ import annotations

from ..errors import kubectl_failure


def map_kubectl_error(
    context: str,
    command: list[str],
    stderr: str,
    returncode: int,
) -> dict[str, str | int]:
    """Map kubectl stderr/exit code to an internal error dict.

    Recognized patterns:
      - "not found" / "NotFound" → unknown_resource
      - "forbidden" / "unauthorized" → access_denied
      - "Ambiguous" → ambiguous_resource
      - Everything else → kubectl_failure (raw)
    """
    stderr_lower = stderr.lower()

    if "ambiguous" in stderr_lower:
        # e.g. "ambiguous resource (please specify the fully qualified name)"
        return {
            "error": "ambiguous_resource",
            "context": context,
            "raw_stderr": stderr,
        }

    if "notfound" in stderr_lower or "not found" in stderr_lower:
        return {
            "error": "unknown_resource",
            "context": context,
            "raw_stderr": stderr,
        }

    if "forbidden" in stderr_lower or "unauthorized" in stderr_lower:
        return {
            "error": "access_denied",
            "context": context,
            "raw_stderr": stderr,
        }

    # Default: surface as raw kubectl failure
    return kubectl_failure(
        context=context,
        command=" ".join(command),
        stderr=stderr,
        exit_code=returncode,
    )
