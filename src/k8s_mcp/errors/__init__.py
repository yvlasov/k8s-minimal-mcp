"""Shared error-response contract per PRD §7.

Every error returns a dict with:
  - context: echoed back from input
  - error: one of the codes below
  - (optional) candidates, hint, suggestions, valid_contexts

Error responses are constructed only via the helpers below so the §7 shape
stays identical everywhere. No tool assembles error dicts ad hoc.
"""

from __future__ import annotations

# Re-export everything from submodules so existing import sites need zero changes.
from .core import (
    ERROR_AMBIGUOUS_RESOURCE,
    ERROR_UNKNOWN_RESOURCE,
    ERROR_VERB_UNSUPPORTED,
    ERROR_NAMESPACE_INVALID,
    ERROR_UNKNOWN_CONTEXT,
    ERROR_ACCESS_DENIED,
    ERROR_KUBECTL_FAILURE,
    ERROR_EXEC_FAILED,
    ERROR_INVALID_MANIFEST,
    ERROR_INVALID_OUTPUT,
    ERROR_INVALID_SELECTOR,
    ERROR_DISCOVERY_FAILURE,
    ERROR_INVALID_JSONPATH_TEMPLATE,
    ERROR_INVALID_GREP_PATTERN,
    ERROR_OBJECT_NOT_FOUND,
    _base,
    access_denied,
    ambiguous_resource,
    discovery_failure,
    exec_failed,
    invalid_grep_pattern,
    invalid_jsonpath_template,
    invalid_manifest,
    invalid_output,
    invalid_selector,
    kubectl_failure,
    namespace_invalid,
    object_not_found,
    unknown_context,
    unknown_resource,
    verb_unsupported,
)
from .files import (
    ERROR_FILE_EXISTS,
    ERROR_FILE_READ_FAILED,
    ERROR_FILE_WRITE_FAILED,
    ERROR_UNSAFE_PATH,
    file_exists,
    file_read_failed,
    file_write_failed,
    unsafe_path,
)
from .helm import (
    ERROR_HELM_RELEASE_DECODE_FAILED,
    ERROR_HELM_RELEASE_NOT_FOUND,
    helm_release_decode_failed,
    helm_release_not_found,
)

__all__ = [
    # Core error codes
    "ERROR_AMBIGUOUS_RESOURCE",
    "ERROR_UNKNOWN_RESOURCE",
    "ERROR_VERB_UNSUPPORTED",
    "ERROR_NAMESPACE_INVALID",
    "ERROR_UNKNOWN_CONTEXT",
    "ERROR_ACCESS_DENIED",
    "ERROR_KUBECTL_FAILURE",
    "ERROR_EXEC_FAILED",
    "ERROR_INVALID_MANIFEST",
    "ERROR_INVALID_OUTPUT",
    "ERROR_INVALID_SELECTOR",
    "ERROR_DISCOVERY_FAILURE",
    "ERROR_INVALID_JSONPATH_TEMPLATE",
    "ERROR_INVALID_GREP_PATTERN",
    "ERROR_OBJECT_NOT_FOUND",
    # File-I/O error codes
    "ERROR_UNSAFE_PATH",
    "ERROR_FILE_EXISTS",
    "ERROR_FILE_WRITE_FAILED",
    "ERROR_FILE_READ_FAILED",
    # Helm error codes
    "ERROR_HELM_RELEASE_NOT_FOUND",
    "ERROR_HELM_RELEASE_DECODE_FAILED",
    # Core helpers
    "_base",
    "access_denied",
    "ambiguous_resource",
    "discovery_failure",
    "exec_failed",
    "invalid_grep_pattern",
    "invalid_jsonpath_template",
    "invalid_manifest",
    "invalid_output",
    "invalid_selector",
    "kubectl_failure",
    "namespace_invalid",
    "object_not_found",
    "unknown_context",
    "unknown_resource",
    "verb_unsupported",
    # File-I/O helpers
    "file_exists",
    "file_read_failed",
    "file_write_failed",
    "unsafe_path",
    # Helm helpers
    "helm_release_decode_failed",
    "helm_release_not_found",
]
