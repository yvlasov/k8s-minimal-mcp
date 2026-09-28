"""kubectl stderr → internal error codes mapping (PRD §7).

Maps common kubectl failure patterns to our structured error contract.
Called by tools after a non-zero returncode from runner.py.
"""

from __future__ import annotations

from ..errors import (
    authentication_failed,
    kubectl_failure,
    kubectl_invalid_argument,
    kubectl_unreachable,
    object_invalid,
    object_not_found,
)


def map_kubectl_error(
    context: str,
    command: list[str],
    stderr: str,
    returncode: int,
) -> dict[str, str | int]:
    """Map kubectl stderr/exit code to an internal error dict.

    Recognized patterns (first match wins):
      - "ambiguous" → ambiguous_resource
      - "not found" / "NotFound" → object_not_found
      - "unable to connect" / "connection refused" / "no such host" / "dial tcp" → kubectl_unreachable
      - "x509:" / "must be logged in" / "unauthorized" (without "forbidden") → authentication_failed
      - "forbidden" (or "unauthorized" with "forbidden" present) → access_denied
      - "error: unknown flag" / "unknown shorthand flag" / "unknown command" → kubectl_invalid_argument
      - " is invalid: " → object_invalid
      - Everything else → kubectl_failure (raw)
    """
    stderr_lower = stderr.lower()

    if "ambiguous" in stderr_lower:
        return {
            "error": "ambiguous_resource",
            "context": context,
            "raw_stderr": stderr,
        }

    if "notfound" in stderr_lower or "not found" in stderr_lower:
        return object_not_found(
            context=context,
            raw_stderr=stderr,
        )

    if (
        "unable to connect to the server" in stderr_lower
        or "connection refused" in stderr_lower
        or "no such host" in stderr_lower
        or "dial tcp" in stderr_lower
    ):
        return kubectl_unreachable(context=context, raw_stderr=stderr)

    if "forbidden" not in stderr_lower and (
        "unauthorized" in stderr_lower
        or "must be logged in" in stderr_lower
        or "x509:" in stderr_lower
    ):
        return authentication_failed(context=context, raw_stderr=stderr)

    if "forbidden" in stderr_lower or "unauthorized" in stderr_lower:
        return {
            "error": "access_denied",
            "context": context,
            "raw_stderr": stderr,
        }

    if (
        stderr_lower.startswith("error: unknown flag")
        or stderr_lower.startswith("error: unknown shorthand flag")
        or stderr_lower.startswith("error: unknown command")
    ):
        return kubectl_invalid_argument(context=context, raw_stderr=stderr)

    if " is invalid: " in stderr_lower:
        return object_invalid(context=context, raw_stderr=stderr)

    return kubectl_failure(
        context=context,
        command=" ".join(command),
        stderr=stderr,
        exit_code=returncode,
    )
