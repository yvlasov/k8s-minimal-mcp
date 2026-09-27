"""File-I/O errors (FR9/FR10's path/file helpers)."""

from __future__ import annotations

from typing import Any

ERROR_UNSAFE_PATH = "unsafe_path"
ERROR_FILE_EXISTS = "file_exists"
ERROR_FILE_WRITE_FAILED = "file_write_failed"
ERROR_FILE_READ_FAILED = "file_read_failed"


def _base(context: str, code: str) -> dict[str, Any]:
    return {"context": context, "error": code}


def unsafe_path(
    context: str,
    path: str,
    *,
    detail: str | None = None,
) -> dict[str, Any]:
    """k_get_secret_to_file: dst_secret_file failed the path-safety check (e.g. not absolute)."""
    out = _base(context, ERROR_UNSAFE_PATH)
    out["path"] = path
    if detail:
        out["detail"] = detail
    return out


def file_exists(
    context: str,
    path: str,
) -> dict[str, Any]:
    """k_get_secret_to_file: destination file already exists and overwrite is not set."""
    out = _base(context, ERROR_FILE_EXISTS)
    out["path"] = path
    return out


def file_write_failed(
    context: str,
    path: str,
    *,
    detail: str | None = None,
) -> dict[str, Any]:
    """k_get_secret_to_file: writing the decoded Secret to disk failed (permissions, missing parent dir)."""
    out = _base(context, ERROR_FILE_WRITE_FAILED)
    out["path"] = path
    if detail:
        out["detail"] = detail
    return out


def file_read_failed(
    context: str,
    path: str,
    *,
    detail: str | None = None,
) -> dict[str, Any]:
    """k_apply: reading the manifest from src_file failed (missing file, permissions, undecodable content)."""
    out = _base(context, ERROR_FILE_READ_FAILED)
    out["path"] = path
    if detail:
        out["detail"] = detail
    return out
