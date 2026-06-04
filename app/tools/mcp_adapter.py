"""MCP Adapter — proxies external MCP server tools into the ToolRegistry.

Implements TOOLS_MCP_SPEC §4: MCP 适配器协议.

Architecture::

    Agent/Workflow/Domain
           ↓
       ToolRegistry
           ↓
       MCPAdapter (if tool category == "mcp")
           ↓
       MCP Client (JSON-RPC over HTTP/SSE)
           ↓
       External MCP Server
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx

from app.core.errors import (
    ERROR_CODE_SERVICE_UNAVAILABLE,
    make_error,
)
from app.core.logging import get_logger

logger = get_logger("tools.mcp_adapter")


# ---------------------------------------------------------------------------
# Config data model
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class MCPToolConfig:
    """Declaration of a single tool exposed by an MCP server."""

    name: str
    description: str = ""


@dataclass(frozen=True, slots=True)
class MCPServerConfig:
    """Connection config for one MCP server."""

    name: str
    url: str
    transport: str = "sse"  # "sse" | "stdio"
    timeout: float = 30.0
    tools: list[MCPToolConfig] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Adapter (one per MCP server)
# ---------------------------------------------------------------------------

class MCPAdapter:
    """Wraps a single MCP server, exposing its tools as async callables."""

    def __init__(self, config: MCPServerConfig) -> None:
        self._config = config
        self._client: httpx.AsyncClient | None = None

    # -- lifecycle -----------------------------------------------------------

    async def connect(self) -> None:
        """Open HTTP transport to the MCP server."""
        self._client = httpx.AsyncClient(
            base_url=self._config.url,
            timeout=self._config.timeout,
        )
        logger.info(
            "mcp_adapter.connected",
            server=self._config.name,
            url=self._config.url,
        )

    async def close(self) -> None:
        """Close the HTTP transport."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
            logger.info("mcp_adapter.closed", server=self._config.name)

    # -- execution -----------------------------------------------------------

    async def call_tool(self, tool_name: str, **kwargs: Any) -> Any:
        """Execute a tool on the remote MCP server via JSON-RPC."""
        if self._client is None:
            raise make_error(
                ERROR_CODE_SERVICE_UNAVAILABLE,
                f"MCP server '{self._config.name}' not connected",
            )

        payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": kwargs},
            "id": 1,
        }

        try:
            response = await self._client.post("/", json=payload)
            response.raise_for_status()
            result = response.json()

            if "error" in result:
                err = result["error"]
                raise make_error(
                    ERROR_CODE_SERVICE_UNAVAILABLE,
                    f"MCP tool '{tool_name}' error: {err.get('message', 'unknown')}",
                )
            return result.get("result")
        except httpx.HTTPError as exc:
            logger.error(
                "mcp_adapter.call_failed",
                server=self._config.name,
                tool=tool_name,
                error=str(exc),
            )
            raise make_error(
                ERROR_CODE_SERVICE_UNAVAILABLE,
                f"MCP server '{self._config.name}' unreachable: {exc}",
            )

    # -- introspection -------------------------------------------------------

    @property
    def tool_names(self) -> list[str]:
        return [t.name for t in self._config.tools]

    @property
    def config(self) -> MCPServerConfig:
        return self._config

    def make_callable(self, tool_name: str) -> Any:
        """Return an async callable bound to a specific MCP tool name."""

        async def _proxy(**kwargs: Any) -> Any:
            return await self.call_tool(tool_name, **kwargs)

        _proxy.__name__ = f"mcp_{self._config.name}_{tool_name}"
        return _proxy


# ---------------------------------------------------------------------------
# Manager (multiple servers)
# ---------------------------------------------------------------------------

class MCPManager:
    """Manages multiple MCP server adapters and registers their tools."""

    def __init__(self) -> None:
        self._adapters: dict[str, MCPAdapter] = {}

    async def add_server(self, config: MCPServerConfig) -> MCPAdapter:
        """Create, connect, and store an adapter for the given server config."""
        adapter = MCPAdapter(config)
        await adapter.connect()
        self._adapters[config.name] = adapter
        return adapter

    async def close_all(self) -> None:
        """Disconnect all adapters."""
        for adapter in self._adapters.values():
            await adapter.close()
        self._adapters.clear()

    def get_adapter(self, server_name: str) -> MCPAdapter | None:
        return self._adapters.get(server_name)

    def list_adapters(self) -> list[MCPAdapter]:
        return list(self._adapters.values())

    async def register_tools(self, tool_registry: Any) -> int:
        """Register all MCP server tools into the given ToolRegistry.

        Returns the number of tools registered.
        """
        count = 0
        for adapter in self._adapters.values():
            for tool_cfg in adapter.config.tools:
                tool_registry.register(
                    name=tool_cfg.name,
                    fn=adapter.make_callable(tool_cfg.name),
                    description=tool_cfg.description,
                    category="mcp",
                    timeout=adapter.config.timeout,
                )
                count += 1
        logger.info("mcp_manager.tools_registered", count=count)
        return count


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_mcp_manager: MCPManager | None = None


def get_mcp_manager() -> MCPManager:
    """Get or create the global MCPManager singleton."""
    global _mcp_manager
    if _mcp_manager is None:
        _mcp_manager = MCPManager()
    return _mcp_manager


def reset_mcp_manager() -> None:
    """Reset the singleton (for tests only)."""
    global _mcp_manager
    _mcp_manager = None
