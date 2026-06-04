"""Built-in tool registration.

Registers calculator and datetime_now into the given ToolRegistry.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.tools.builtin.calculator import calculator
from app.tools.builtin.datetime_now import datetime_now

if TYPE_CHECKING:
    from app.tools.registry import ToolRegistry


def register_builtin_tools(registry: ToolRegistry) -> int:
    """Register all built-in tools into the registry. Returns count."""
    registry.register(
        name="calculator",
        fn=calculator,
        description="Basic arithmetic: add, sub, mul, div",
        category="tool",
        timeout=10.0,
    )
    registry.register(
        name="datetime_now",
        fn=datetime_now,
        description="Get current date/time in ISO format",
        category="tool",
        timeout=5.0,
    )
    return 2
