"""Tool Registry — central capability store for Tools / Skills / MCP proxies.

Implements TOOLS_MCP_SPEC §2: ToolRegistry + ToolDefinition + @tool decorator.

Dependency: F01 (app/core/di.py for DI registration at bootstrap).
"""

from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass, field
from typing import Any, Callable

from app.core.errors import (
    ERROR_CODE_AGENT_TOOL_NOT_FOUND,
    ERROR_CODE_TIMEOUT,
    AppError,
    make_error,
)
from app.core.logging import get_logger

logger = get_logger("tools.registry")


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ToolDefinition:
    """Immutable metadata + callable for a registered tool."""

    name: str
    description: str
    category: str  # "tool" | "skill" | "mcp"
    parameters: dict[str, Any]  # JSON Schema
    return_type: type
    fn: Callable[..., Any]
    timeout: float = 30.0
    requires_auth: bool = False


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class ToolRegistry:
    """Central store for all callable tools (tool / skill / mcp)."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    # -- write ---------------------------------------------------------------

    def register(
        self,
        name: str,
        fn: Callable[..., Any],
        *,
        description: str = "",
        category: str = "tool",
        parameters: dict[str, Any] | None = None,
        return_type: type = Any,
        timeout: float = 30.0,
        requires_auth: bool = False,
    ) -> None:
        """Register a tool, skill function, or MCP proxy."""
        if parameters is None:
            parameters = _extract_parameters(fn)

        if name in self._tools:
            logger.warning("tools.registry.duplicate", name=name, category=category)

        self._tools[name] = ToolDefinition(
            name=name,
            description=description,
            category=category,
            parameters=parameters,
            return_type=return_type,
            fn=fn,
            timeout=timeout,
            requires_auth=requires_auth,
        )
        logger.debug("tools.registry.registered", name=name, category=category)

    def override(self, name: str, fn: Callable[..., Any]) -> None:
        """Replace a tool's implementation (for testing)."""
        if name not in self._tools:
            raise make_error(
                ERROR_CODE_AGENT_TOOL_NOT_FOUND,
                f"Tool '{name}' not registered",
            )
        old = self._tools[name]
        self._tools[name] = ToolDefinition(
            name=old.name,
            description=old.description,
            category=old.category,
            parameters=old.parameters,
            return_type=old.return_type,
            fn=fn,
            timeout=old.timeout,
            requires_auth=old.requires_auth,
        )
        logger.info("tools.registry.overridden", name=name)

    # -- read ----------------------------------------------------------------

    def get(self, name: str) -> ToolDefinition:
        """Retrieve a tool by name. Raises AGENT_TOOL_NOT_FOUND if missing."""
        try:
            return self._tools[name]
        except KeyError:
            raise make_error(
                ERROR_CODE_AGENT_TOOL_NOT_FOUND,
                f"Tool '{name}' not registered",
            )

    def list_tools(self, category: str | None = None) -> list[ToolDefinition]:
        """List all registered tools, optionally filtered by category."""
        if category is None:
            return list(self._tools.values())
        return [t for t in self._tools.values() if t.category == category]

    def has(self, name: str) -> bool:
        """Check whether a tool is registered (without raising)."""
        return name in self._tools

    # -- execute -------------------------------------------------------------

    async def call(self, name: str, **kwargs: Any) -> Any:
        """Execute a tool by name with timeout protection."""
        tool = self.get(name)

        try:
            if asyncio.iscoroutinefunction(tool.fn):
                result = await asyncio.wait_for(tool.fn(**kwargs), timeout=tool.timeout)
            else:
                result = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(None, lambda: tool.fn(**kwargs)),
                    timeout=tool.timeout,
                )
            return result
        except asyncio.TimeoutError:
            raise make_error(
                ERROR_CODE_TIMEOUT,
                f"Tool '{name}' timed out after {tool.timeout}s",
            )
        except AppError:
            raise
        except Exception as exc:
            raise make_error(
                ERROR_CODE_AGENT_TOOL_NOT_FOUND,
                f"Tool '{name}' execution failed: {exc}",
                detail=str(exc),
            )

    # -- lifecycle -----------------------------------------------------------

    def clear(self) -> None:
        """Remove all registered tools."""
        self._tools.clear()


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_instance: ToolRegistry | None = None


def get_tool_registry() -> ToolRegistry:
    """Get or create the global ToolRegistry singleton."""
    global _instance
    if _instance is None:
        _instance = ToolRegistry()
    return _instance


def reset_tool_registry() -> None:
    """Reset the singleton (for tests only)."""
    global _instance
    if _instance is not None:
        _instance.clear()
    _instance = None


# ---------------------------------------------------------------------------
# @tool decorator
# ---------------------------------------------------------------------------

def tool(
    *,
    name: str | None = None,
    description: str = "",
    category: str = "tool",
    timeout: float = 30.0,
    requires_auth: bool = False,
) -> Callable[..., Callable[..., Any]]:
    """Decorator to auto-register an async/sync function as a tool.

    Usage::

        @tool(name="my_tool", description="Does something")
        async def my_tool(arg: str) -> str:
            return arg.upper()
    """

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        tool_name = name or fn.__name__
        tool_desc = description or (fn.__doc__ or "").strip().split("\n")[0]
        registry = get_tool_registry()
        registry.register(
            tool_name,
            fn,
            description=tool_desc,
            category=category,
            timeout=timeout,
            requires_auth=requires_auth,
        )
        return fn

    return decorator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_parameters(fn: Callable[..., Any]) -> dict[str, Any]:
    """Best-effort JSON Schema extraction from function signature."""
    # Resolve string annotations (from __future__ import annotations)
    try:
        hints = _resolve_type_hints(fn)
    except Exception:
        hints = {}

    sig = inspect.signature(fn)
    properties: dict[str, Any] = {}
    required: list[str] = []

    type_map: dict[type, str] = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        list: "array",
        dict: "object",
    }

    for param_name, param in sig.parameters.items():
        if param_name in ("self", "cls"):
            continue

        json_type = "string"
        hint = hints.get(param_name)
        if hint is not None:
            origin = getattr(hint, "__origin__", None)
            if origin is None and isinstance(hint, type):
                json_type = type_map.get(hint, "string")
            else:
                json_type = "string"

        prop: dict[str, Any] = {"type": json_type}
        properties[param_name] = prop

        if param.default is inspect.Parameter.empty:
            required.append(param_name)

    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
    }
    if required:
        schema["required"] = required
    return schema


def _resolve_type_hints(fn: Callable[..., Any]) -> dict[str, Any]:
    """Resolve type hints, handling 'from __future__ import annotations'."""
    import typing
    try:
        return typing.get_type_hints(fn)
    except Exception:
        return getattr(fn, "__annotations__", {})
