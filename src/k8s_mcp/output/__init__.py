"""Output module — response shaping pipeline (R4, R9, R10, R3).

Pipeline: pruning → bounding → envelope
Applied uniformly at the output boundary, not per-tool.
"""

from .pruning import prune
from .bounding import bound_get_names, bound_logs, apply_output_format
from .envelope import envelope, envelope_list_contexts

__all__ = [
    "prune",
    "bound_get_names",
    "bound_logs",
    "apply_output_format",
    "envelope",
    "envelope_list_contexts",
]
