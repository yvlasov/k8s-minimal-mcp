"""R9: Field pruning for JSON responses.

Strip unconditionally:
  - metadata.managedFields
  - metadata.annotations["kubectl.kubernetes.io/last-applied-configuration"]
  - metadata.uid
  - metadata.generation
  - metadata.resourceVersion

Strip `status` unless the resource kind is one where status carries debugging
signal (pods, deployments, statefulsets, jobs, CRDs with conditions) or the
caller explicitly requests it.

Pruning is stateless — always fresh from the API server, no caching.
"""

from __future__ import annotations

from typing import Any

# Kinds where status is retained by default (carries debugging signal)
_STATUS_KINDS = frozenset({
    "Pod", "Deployment", "StatefulSet", "Job", "CronJob",
    "ReplicaSet", "DaemonSet", "Node", "PersistentVolumeClaim",
    "Service", "Ingress", "NetworkPolicy",
})

# CRD kinds that typically have conditions in status
_CONDITION_KINDS = frozenset({"CustomResourceDefinition", "Certificate", "CiliumNetworkPolicy"})

_UNCONDITIONAL_STRIP_PATHS: list[list[str]] = [
    ["metadata", "managedFields"],
    ["metadata", "uid"],
    ["metadata", "generation"],
    ["metadata", "resourceVersion"],
]

_LAST_APPLIED_ANNOTATION = "kubectl.kubernetes.io/last-applied-configuration"


def prune(data: Any, *, kind: str | None = None, keep_status: bool = False) -> Any:
    """Apply R9 field pruning to a JSON-serializable data structure.

    Args:
        data: parsed JSON from kubectl -o json.
        kind: resource kind (e.g. "Pod", "Deployment"). Used for status retention logic.
        keep_status: if True, never strip the status field.

    Returns:
        Pruned copy of the data.
    """
    if not isinstance(data, dict):
        return data

    result = _deep_copy_dict(data)

    # Strip unconditional fields
    for path in _UNCONDITIONAL_STRIP_PATHS:
        _strip_path(result, path)

    # Strip last-applied-configuration annotation
    metadata = result.get("metadata")
    if isinstance(metadata, dict):
        annotations = metadata.get("annotations")
        if isinstance(annotations, dict):
            annotations.pop(_LAST_APPLIED_ANNOTATION, None)

    # Status retention
    if "status" in result:
        if not keep_status and kind:
            if kind not in _STATUS_KINDS and kind not in _CONDITION_KINDS:
                result.pop("status")
        elif not keep_status and not kind:
            # No kind info — default to stripping status
            result.pop("status")

    return result


def _deep_copy_dict(d: dict) -> dict:
    """Copy: top-level keys + metadata sub-dict (including annotations)."""
    result = {}
    for k, v in d.items():
        if k == "metadata" and isinstance(v, dict):
            metadata_copy = dict(v)
            if "annotations" in metadata_copy and isinstance(metadata_copy["annotations"], dict):
                metadata_copy["annotations"] = dict(metadata_copy["annotations"])
            result[k] = metadata_copy
        else:
            result[k] = v
    return result


def _strip_path(data: dict, path: list[str]) -> None:
    """Navigate to a nested key and delete it, if it exists."""
    current = data
    for segment in path[:-1]:
        if isinstance(current, dict) and segment in current:
            current = current[segment]
        else:
            return
    if isinstance(current, dict):
        current.pop(path[-1], None)
