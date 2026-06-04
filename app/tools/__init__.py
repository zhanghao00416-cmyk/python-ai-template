"""app.tools — Capability layer: ToolRegistry, MCP adapter, built-in tools.

Public API::

    from app.tools import ToolRegistry, ToolDefinition, tool, get_tool_registry
"""

from app.tools.registry import (
    ToolDefinition,
    ToolRegistry,
    get_tool_registry,
    reset_tool_registry,
    tool,
)

__all__ = [
    "ToolDefinition",
    "ToolRegistry",
    "get_tool_registry",
    "reset_tool_registry",
    "tool",
]
