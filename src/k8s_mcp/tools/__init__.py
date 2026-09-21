"""Tools module — verb-based MCP tools."""

from .get import handle_get
from .logs import handle_logs
from .apply import handle_apply
from .patch import handle_patch
from .delete import handle_delete
from .exec_ import handle_exec
from .contexts import handle_list_contexts
from .describe import handle_describe
from .list_resources import handle_list_resources

__all__ = [
    "handle_get",
    "handle_logs",
    "handle_apply",
    "handle_patch",
    "handle_delete",
    "handle_exec",
    "handle_list_contexts",
    "handle_describe",
    "handle_list_resources",
]
