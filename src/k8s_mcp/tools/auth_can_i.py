"""FR13: k_auth_can_i — thin wrapper over kubectl auth can-i for RBAC effective-permission checks.

Must call run_kubectl directly (not run_kubectl_checked) because auth can-i uses
exit code as its answer channel (0=allowed, 1=denied), the opposite of every
other kubectl subcommand this project wraps.

Named explicitly in PRD §15 FR13 and SPEC.md §8 FR13 so a future reader
doesn't "fix" this call site to route through _checked and silently break it.
"""

from __future__ import annotations

from typing import Any

from ..kubectl.runner import run_kubectl


def _build_auth_args(
    verb: str | None,
    resource_with_name: str | None,
    namespace: str | None,
    as_user: str | None,
    as_group: list[str] | None,
    list_all: bool,
) -> list[str]:
    """Build kubectl auth can-i arguments in the correct order."""
    args: list[str] = ["auth", "can-i"]
    if not list_all:
        if verb:
            args.append(verb)
        if resource_with_name:
            args.append(resource_with_name)
    if namespace:
        args.extend(["-n", namespace])
    if as_user:
        args.extend(["--as", as_user])
    if as_group:
        for g in as_group:
            args.extend(["--as-group", g])
    if list_all:
        args.append("--list")
    return args


def _parse_list_output(stdout: str) -> dict[str, list[str]]:
    """Parse kubectl auth can-i --list table output into {resource: [verbs]} entries.

    The --list table format has a header line followed by rows like:
        Resources Granted
        --------------- ---------
        pods            [get, list, watch]
        secrets         [get]
    """
    permissions: dict[str, list[str]] = {}
    lines = stdout.strip().splitlines()
    if len(lines) < 3:
        return permissions

    for line in lines[2:]:
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) >= 2:
            resource = parts[0]
            verbs_str = " ".join(parts[1:])
            if verbs_str.startswith("[") and verbs_str.endswith("]"):
                verbs = verbs_str[1:-1].replace(" ", "").split(",")
                permissions[resource] = verbs

    return permissions


def handle_auth_can_i(
    context: str,
    verb: str | None = None,
    resource: str | None = None,
    name: str | None = None,
    namespace: str | None = None,
    as_user: str | None = None,
    as_group: list[str] | None = None,
    list_all: bool = False,
    *,
    discovery_cache: object | None = None,
) -> dict[str, Any]:
    """Handle k_auth_can_i: single-check or --list mode.

    Single-check mode returns {"allowed": true|false} plus the literal command run.
    List mode returns {"permissions": {"<resource>": ["<verb>", ...]}}.
    """
    resource_with_name = f"{resource}/{name}" if name else resource
    args = _build_auth_args(verb, resource_with_name, namespace, as_user, as_group, list_all)
    result = run_kubectl(context, args, output_format=None)

    if "error" in result:
        from ..output import envelope
        from ..errors import kubectl_failure
        err = kubectl_failure(context, " ".join(result.get("command", args)), result["error"])
        return envelope(err, context, "k_auth_can_i", success=False)

    returncode = result.get("returncode")
    stdout = result.get("stdout", "")
    stderr = result.get("stderr", "")
    command = result.get("command", args)

    if list_all:
        if returncode != 0:
            from ..output import envelope
            from ..errors import kubectl_failure
            err = kubectl_failure(context, " ".join(command), stderr)
            return envelope(err, context, "k_auth_can_i", success=False)
        permissions = _parse_list_output(stdout)
        from ..output import envelope
        return envelope({"permissions": permissions, "command": command}, context, "k_auth_can_i", success=True)

    if returncode == 0:
        from ..output import envelope
        return envelope({"allowed": True, "command": command}, context, "k_auth_can_i", success=True)
    elif returncode == 1:
        from ..output import envelope
        return envelope({"allowed": False, "command": command}, context, "k_auth_can_i", success=True)
    else:
        from ..output import envelope
        from ..errors import kubectl_failure
        err = kubectl_failure(context, " ".join(command), stderr, exit_code=returncode)
        return envelope(err, context, "k_auth_can_i", success=False)
