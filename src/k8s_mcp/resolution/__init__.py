"""Resolution module — resource name → GVK lookup.

Exports:
  - ResourceMeta model
  - load_core_table()
  - DiscoveryCache
  - resolve() — two-tier lookup (core table + discovery)
  - validate() — pre-execution validation (R8)
"""

from .models import ResourceMeta
from .core_table import load_core_table
from .discovery import DiscoveryCache
from .resolver import resolve, validate

__all__ = [
    "ResourceMeta",
    "load_core_table",
    "DiscoveryCache",
    "resolve",
    "validate",
]
