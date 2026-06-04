"""F10 — Tools Registry + MCP Adapter + Skill Registry tests.

Covers:
- ToolRegistry: register, get, list_tools, call, override, timeout, errors
- @tool decorator
- Built-in tools: calculator, datetime_now
- MCPAdapter / MCPManager: connection lifecycle, tool registration
- SkillRegistry: load_from_yaml, get, list_skills, run, tool validation
- SkillContext / SkillResult
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from app.core.errors import AppError
from app.tools.registry import (
    ToolDefinition,
    ToolRegistry,
    tool,
    get_tool_registry,
    reset_tool_registry,
)
from app.tools.mcp_adapter import (
    MCPAdapter,
    MCPManager,
    MCPServerConfig,
    MCPToolConfig,
    get_mcp_manager,
    reset_mcp_manager,
)
from app.tools.builtin.calculator import calculator
from app.tools.builtin.datetime_now import datetime_now
from app.tools.builtin import register_builtin_tools
from app.services.skill_registry import (
    SkillContext,
    SkillDefinition,
    SkillRegistry,
    SkillResult,
    reset_skill_registry,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def registry() -> ToolRegistry:
    """Fresh ToolRegistry per test."""
    return ToolRegistry()


@pytest.fixture
def skill_registry(registry: ToolRegistry) -> SkillRegistry:
    """SkillRegistry backed by a fresh ToolRegistry."""
    return SkillRegistry(tools=registry)


@pytest.fixture(autouse=True)
def _reset_singletons():
    """Reset global singletons between tests."""
    yield
    reset_tool_registry()
    reset_skill_registry()
    reset_mcp_manager()


# ===========================================================================
# ToolRegistry
# ===========================================================================

class TestToolRegistry:
    """ToolRegistry — register / get / list / call / override."""

    def test_register_and_get(self, registry: ToolRegistry):
        async def echo(msg: str) -> str:
            return msg

        registry.register("echo", echo, description="Echo tool", category="tool")

        td = registry.get("echo")
        assert td.name == "echo"
        assert td.description == "Echo tool"
        assert td.category == "tool"
        assert td.timeout == 30.0

    def test_register_with_custom_timeout(self, registry: ToolRegistry):
        async def slow_tool() -> str:
            return "done"

        registry.register("slow", slow_tool, timeout=60.0)
        assert registry.get("slow").timeout == 60.0

    def test_get_missing_raises(self, registry: ToolRegistry):
        with pytest.raises(AppError) as exc_info:
            registry.get("nonexistent")
        assert exc_info.value.code == 7002  # AGENT_TOOL_NOT_FOUND

    def test_list_tools_all(self, registry: ToolRegistry):
        async def a() -> None: pass
        async def b() -> None: pass

        registry.register("a", a)
        registry.register("b", b, category="mcp")

        all_tools = registry.list_tools()
        assert len(all_tools) == 2

    def test_list_tools_by_category(self, registry: ToolRegistry):
        async def a() -> None: pass
        async def b() -> None: pass

        registry.register("a", a, category="tool")
        registry.register("b", b, category="mcp")

        tools = registry.list_tools(category="tool")
        assert len(tools) == 1
        assert tools[0].name == "a"

    def test_list_tools_empty_category(self, registry: ToolRegistry):
        assert registry.list_tools(category="skill") == []

    def test_has(self, registry: ToolRegistry):
        async def dummy() -> None: pass

        assert registry.has("dummy") is False
        registry.register("dummy", dummy)
        assert registry.has("dummy") is True

    @pytest.mark.asyncio
    async def test_call_async(self, registry: ToolRegistry):
        async def add(a: int, b: int) -> int:
            return a + b

        registry.register("add", add)
        result = await registry.call("add", a=2, b=3)
        assert result == 5

    @pytest.mark.asyncio
    async def test_call_sync_function(self, registry: ToolRegistry):
        def greet(person: str) -> str:
            return f"hello {person}"

        registry.register("greet", greet)
        result = await registry.call("greet", person="world")
        assert result == "hello world"

    @pytest.mark.asyncio
    async def test_call_missing_tool_raises(self, registry: ToolRegistry):
        with pytest.raises(AppError) as exc_info:
            await registry.call("nope")
        assert exc_info.value.code == 7002

    @pytest.mark.asyncio
    async def test_call_timeout(self, registry: ToolRegistry):
        async def slow() -> str:
            await asyncio.sleep(10)
            return "never"

        registry.register("slow", slow, timeout=0.05)
        with pytest.raises(AppError) as exc_info:
            await registry.call("slow")
        assert exc_info.value.code == 4  # TIMEOUT_ERROR

    @pytest.mark.asyncio
    async def test_call_propagates_app_error(self, registry: ToolRegistry):
        async def fail() -> None:
            raise AppError(7002, "custom error")

        registry.register("fail", fail)
        with pytest.raises(AppError) as exc_info:
            await registry.call("fail")
        assert exc_info.value.code == 7002
        assert exc_info.value.message == "custom error"

    @pytest.mark.asyncio
    async def test_call_generic_exception(self, registry: ToolRegistry):
        async def boom() -> None:
            raise RuntimeError("kaboom")

        registry.register("boom", boom)
        with pytest.raises(AppError):
            await registry.call("boom")

    def test_override(self, registry: ToolRegistry):
        async def original() -> str:
            return "original"

        async def patched() -> str:
            return "patched"

        registry.register("tool1", original)
        assert registry.get("tool1").fn is original

        registry.override("tool1", patched)
        assert registry.get("tool1").fn is patched
        # Metadata preserved
        assert registry.get("tool1").name == "tool1"

    def test_override_missing_raises(self, registry: ToolRegistry):
        with pytest.raises(AppError) as exc_info:
            registry.override("nonexistent", lambda: None)
        assert exc_info.value.code == 7002

    def test_clear(self, registry: ToolRegistry):
        async def dummy() -> None: pass

        registry.register("x", dummy)
        assert len(registry.list_tools()) == 1

        registry.clear()
        assert len(registry.list_tools()) == 0

    def test_parameters_auto_extracted(self, registry: ToolRegistry):
        async def typed(a: int, b: str, c: bool = True) -> None:
            pass

        registry.register("typed", typed)
        params = registry.get("typed").parameters
        assert params["type"] == "object"
        assert "a" in params["properties"]
        # typing.get_type_hints resolves string annotations
        assert params["properties"]["a"]["type"] == "integer"
        assert params["properties"]["b"]["type"] == "string"
        assert "a" in params["required"]
        assert "b" in params["required"]
        assert "c" not in params["required"]


# ===========================================================================
# Singleton
# ===========================================================================

class TestToolRegistrySingleton:

    def test_get_returns_same_instance(self):
        r1 = get_tool_registry()
        r2 = get_tool_registry()
        assert r1 is r2

    def test_reset_creates_new_instance(self):
        r1 = get_tool_registry()
        reset_tool_registry()
        r2 = get_tool_registry()
        assert r1 is not r2


# ===========================================================================
# @tool decorator
# ===========================================================================

class TestToolDecorator:

    def test_decorator_registers_tool(self):
        @tool(name="my_tool", description="My tool")
        async def my_tool(x: str) -> str:
            return x

        reg = get_tool_registry()
        assert reg.has("my_tool")
        td = reg.get("my_tool")
        assert td.name == "my_tool"
        assert td.description == "My tool"

    def test_decorator_uses_function_name(self):
        @tool()
        async def auto_name() -> None:
            """Auto description from docstring."""
            pass

        reg = get_tool_registry()
        assert reg.has("auto_name")
        assert "Auto description" in reg.get("auto_name").description

    def test_decorator_preserves_function(self):
        @tool(name="preserved")
        async def my_func() -> str:
            return "original"

        # Decorator returns original function
        assert asyncio.iscoroutinefunction(my_func)


# ===========================================================================
# Built-in tools
# ===========================================================================

class TestBuiltinCalculator:

    @pytest.mark.asyncio
    async def test_add(self):
        assert await calculator("add", 2, 3) == 5.0

    @pytest.mark.asyncio
    async def test_sub(self):
        assert await calculator("sub", 10, 4) == 6.0

    @pytest.mark.asyncio
    async def test_mul(self):
        assert await calculator("mul", 3, 7) == 21.0

    @pytest.mark.asyncio
    async def test_div(self):
        assert await calculator("div", 10, 4) == 2.5

    @pytest.mark.asyncio
    async def test_symbol_operators(self):
        assert await calculator("+", 1, 2) == 3.0
        assert await calculator("*", 3, 4) == 12.0

    @pytest.mark.asyncio
    async def test_division_by_zero(self):
        with pytest.raises(AppError) as exc_info:
            await calculator("div", 1, 0)
        assert exc_info.value.code == 5  # VALIDATION_ERROR

    @pytest.mark.asyncio
    async def test_unknown_operation(self):
        with pytest.raises(AppError) as exc_info:
            await calculator("mod", 1, 2)
        assert exc_info.value.code == 5


class TestBuiltinDatetime:

    @pytest.mark.asyncio
    async def test_utc(self):
        result = await datetime_now("UTC")
        assert "iso" in result
        assert "date" in result
        assert "time" in result
        assert result["tz"] == "UTC"

    @pytest.mark.asyncio
    async def test_local(self):
        result = await datetime_now("local")
        assert result["tz"] == "local"
        assert len(result["date"]) == 10  # YYYY-MM-DD


class TestBuiltinRegistration:

    def test_register_builtin_tools(self, registry: ToolRegistry):
        count = register_builtin_tools(registry)
        assert count == 2
        assert registry.has("calculator")
        assert registry.has("datetime_now")
        assert registry.get("calculator").category == "tool"


# ===========================================================================
# MCPAdapter
# ===========================================================================

class TestMCPAdapter:

    @pytest.fixture
    def server_config(self) -> MCPServerConfig:
        return MCPServerConfig(
            name="test_server",
            url="http://localhost:9999/mcp",
            transport="sse",
            timeout=5.0,
            tools=[
                MCPToolConfig(name="web_search", description="Search the web"),
            ],
        )

    @pytest.fixture
    def adapter(self, server_config: MCPServerConfig) -> MCPAdapter:
        return MCPAdapter(server_config)

    @pytest.mark.asyncio
    async def test_connect_and_close(self, adapter: MCPAdapter):
        await adapter.connect()
        assert adapter._client is not None
        await adapter.close()
        assert adapter._client is None

    @pytest.mark.asyncio
    async def test_call_without_connect_raises(self, adapter: MCPAdapter):
        with pytest.raises(AppError) as exc_info:
            await adapter.call_tool("web_search", query="test")
        assert exc_info.value.code == 3  # SERVICE_UNAVAILABLE

    @pytest.mark.asyncio
    async def test_call_with_mock_response(self, adapter: MCPAdapter):
        await adapter.connect()

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"result": [{"text": "found"}]}

        with patch.object(adapter._client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            result = await adapter.call_tool("web_search", query="test")

        assert result == [{"text": "found"}]
        await adapter.close()

    @pytest.mark.asyncio
    async def test_call_server_error(self, adapter: MCPAdapter):
        await adapter.connect()

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"error": {"message": "internal"}}

        with patch.object(adapter._client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            with pytest.raises(AppError) as exc_info:
                await adapter.call_tool("web_search")
            assert exc_info.value.code == 3

        await adapter.close()

    def test_tool_names(self, adapter: MCPAdapter):
        assert adapter.tool_names == ["web_search"]

    def test_config_property(self, adapter: MCPAdapter, server_config: MCPServerConfig):
        assert adapter.config is server_config

    @pytest.mark.asyncio
    async def test_make_callable(self, adapter: MCPAdapter):
        await adapter.connect()

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"result": "ok"}

        with patch.object(adapter._client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            fn = adapter.make_callable("web_search")
            result = await fn(query="hello")

        assert result == "ok"
        await adapter.close()


# ===========================================================================
# MCPManager
# ===========================================================================

class TestMCPManager:

    @pytest.fixture
    def manager(self) -> MCPManager:
        return MCPManager()

    @pytest.fixture
    def registry(self) -> ToolRegistry:
        return ToolRegistry()

    @pytest.mark.asyncio
    async def test_add_server_and_register(self, manager: MCPManager, registry: ToolRegistry):
        config = MCPServerConfig(
            name="srv1",
            url="http://localhost:9999/mcp",
            timeout=5.0,
            tools=[MCPToolConfig(name="t1", description="tool 1")],
        )

        with patch("app.tools.mcp_adapter.httpx.AsyncClient", return_value=AsyncMock()):
            await manager.add_server(config)
            count = await manager.register_tools(registry)

        assert count == 1
        assert registry.has("t1")
        assert registry.get("t1").category == "mcp"

        await manager.close_all()

    @pytest.mark.asyncio
    async def test_close_all(self, manager: MCPManager):
        config = MCPServerConfig(
            name="srv2", url="http://localhost:9999/mcp", timeout=5.0
        )
        with patch("app.tools.mcp_adapter.httpx.AsyncClient", return_value=AsyncMock()):
            await manager.add_server(config)

        await manager.close_all()
        assert manager.list_adapters() == []

    @pytest.mark.asyncio
    async def test_get_adapter(self, manager: MCPManager):
        config = MCPServerConfig(
            name="srv3", url="http://localhost:9999/mcp", timeout=5.0
        )
        with patch("app.tools.mcp_adapter.httpx.AsyncClient", return_value=AsyncMock()):
            adapter = await manager.add_server(config)

        assert manager.get_adapter("srv3") is adapter
        assert manager.get_adapter("nonexistent") is None
        await manager.close_all()

    @pytest.mark.asyncio
    async def test_singleton(self):
        m1 = get_mcp_manager()
        m2 = get_mcp_manager()
        assert m1 is m2
        reset_mcp_manager()
        m3 = get_mcp_manager()
        assert m1 is not m3


# ===========================================================================
# SkillRegistry
# ===========================================================================

class TestSkillRegistry:
    """SkillRegistry — load, get, list, run, tool validation."""

    @pytest.fixture
    def tools_with_builtins(self) -> ToolRegistry:
        """ToolRegistry with built-in tools registered."""
        reg = ToolRegistry()
        register_builtin_tools(reg)
        return reg

    @pytest.fixture
    def skill_reg(self, tools_with_builtins: ToolRegistry) -> SkillRegistry:
        return SkillRegistry(tools=tools_with_builtins)

    @pytest.fixture
    def tmp_skill_yaml(self, tmp_path: Path) -> Path:
        """Create a temporary skill YAML for testing."""
        yaml_content = """\
id: test_skill
description: "A test skill"
prompt: prompts/skills/test.md
tools:
  - calculator
  - datetime_now
kb_scope:
  collection: general
constraints:
  max_citations: 5
execution: fixed
"""
        skill_file = tmp_path / "test_skill.yaml"
        skill_file.write_text(yaml_content, encoding="utf-8")
        return skill_file

    @pytest.fixture
    def tmp_skill_yaml_invalid_ref(self, tmp_path: Path) -> Path:
        """Skill YAML referencing a non-existent tool."""
        yaml_content = """\
id: bad_skill
description: "References unknown tool"
prompt: prompts/skills/bad.md
tools:
  - nonexistent_tool
execution: fixed
"""
        skill_file = tmp_path / "bad_skill.yaml"
        skill_file.write_text(yaml_content, encoding="utf-8")
        return skill_file

    def test_load_from_yaml(self, skill_reg: SkillRegistry, tmp_skill_yaml: Path):
        sd = skill_reg.load_from_yaml(str(tmp_skill_yaml))
        assert sd.id == "test_skill"
        assert sd.description == "A test skill"
        assert sd.tools == ["calculator", "datetime_now"]
        assert sd.kb_scope == {"collection": "general"}
        assert sd.constraints == {"max_citations": 5}
        assert sd.execution == "fixed"

    def test_load_missing_file_raises(self, skill_reg: SkillRegistry):
        with pytest.raises(AppError) as exc_info:
            skill_reg.load_from_yaml("/nonexistent/path.yaml")
        assert exc_info.value.code == 5  # VALIDATION_ERROR

    def test_load_invalid_tool_ref_raises(
        self, skill_reg: SkillRegistry, tmp_skill_yaml_invalid_ref: Path
    ):
        with pytest.raises(AppError) as exc_info:
            skill_reg.load_from_yaml(str(tmp_skill_yaml_invalid_ref))
        assert exc_info.value.code == 7002  # AGENT_TOOL_NOT_FOUND

    def test_load_empty_yaml_raises(self, skill_reg: SkillRegistry, tmp_path: Path):
        f = tmp_path / "empty.yaml"
        f.write_text("", encoding="utf-8")
        with pytest.raises(AppError):
            skill_reg.load_from_yaml(str(f))

    def test_load_missing_id_raises(self, skill_reg: SkillRegistry, tmp_path: Path):
        f = tmp_path / "no_id.yaml"
        f.write_text("description: no id", encoding="utf-8")
        with pytest.raises(AppError):
            skill_reg.load_from_yaml(str(f))

    def test_get(self, skill_reg: SkillRegistry, tmp_skill_yaml: Path):
        skill_reg.load_from_yaml(str(tmp_skill_yaml))
        sd = skill_reg.get("test_skill")
        assert sd.id == "test_skill"

    def test_get_missing_raises(self, skill_reg: SkillRegistry):
        with pytest.raises(AppError) as exc_info:
            skill_reg.get("nonexistent")
        assert exc_info.value.code == 7002

    def test_list_skills(self, skill_reg: SkillRegistry, tmp_skill_yaml: Path):
        assert skill_reg.list_skills() == []
        skill_reg.load_from_yaml(str(tmp_skill_yaml))
        assert len(skill_reg.list_skills()) == 1

    def test_has(self, skill_reg: SkillRegistry, tmp_skill_yaml: Path):
        assert skill_reg.has("test_skill") is False
        skill_reg.load_from_yaml(str(tmp_skill_yaml))
        assert skill_reg.has("test_skill") is True

    @pytest.mark.asyncio
    async def test_run(self, skill_reg: SkillRegistry, tmp_skill_yaml: Path, tmp_path: Path):
        # Create a prompt file so run() can load it
        prompts_dir = tmp_path / "prompts" / "skills"
        prompts_dir.mkdir(parents=True)
        (prompts_dir / "test.md").write_text("You are a helpful assistant.", encoding="utf-8")

        # Patch prompt path to use tmp
        skill_reg.load_from_yaml(str(tmp_skill_yaml))
        # Override prompt_path to tmp location
        sd = skill_reg.get("test_skill")
        object.__setattr__(sd, "prompt_path", str(prompts_dir / "test.md"))
        skill_reg._skills["test_skill"] = sd

        ctx = SkillContext(user_message="hello", session_id="s1")
        result = await skill_reg.run("test_skill", ctx)

        assert isinstance(result, SkillResult)
        assert result.skill_id == "test_skill"
        assert result.prompt == "You are a helpful assistant."
        assert result.available_tools == ["calculator", "datetime_now"]

    @pytest.mark.asyncio
    async def test_run_extra_tools_union(self, skill_reg: SkillRegistry, tmp_skill_yaml: Path):
        skill_reg.load_from_yaml(str(tmp_skill_yaml))
        ctx = SkillContext(
            user_message="hello",
            extra_tools=["http_call"],
        )
        result = await skill_reg.run("test_skill", ctx)
        assert "http_call" in result.available_tools
        assert "calculator" in result.available_tools

    @pytest.mark.asyncio
    async def test_run_missing_skill_raises(self, skill_reg: SkillRegistry):
        ctx = SkillContext(user_message="hello")
        with pytest.raises(AppError) as exc_info:
            await skill_reg.run("nonexistent", ctx)
        assert exc_info.value.code == 7002

    @pytest.mark.asyncio
    async def test_run_missing_prompt_file(self, skill_reg: SkillRegistry, tmp_skill_yaml: Path):
        skill_reg.load_from_yaml(str(tmp_skill_yaml))
        ctx = SkillContext(user_message="hello")
        result = await skill_reg.run("test_skill", ctx)
        assert "not found" in result.prompt

    def test_clear(self, skill_reg: SkillRegistry, tmp_skill_yaml: Path):
        skill_reg.load_from_yaml(str(tmp_skill_yaml))
        assert len(skill_reg.list_skills()) == 1
        skill_reg.clear()
        assert len(skill_reg.list_skills()) == 0


# ===========================================================================
# SkillDefinition / SkillContext / SkillResult data classes
# ===========================================================================

class TestDataClasses:

    def test_skill_definition_frozen(self):
        sd = SkillDefinition(
            id="s1", description="d", prompt_path="p", tools=["t1"]
        )
        assert sd.id == "s1"
        assert sd.execution == "fixed"
        # frozen=True → cannot set attributes
        with pytest.raises(AttributeError):
            sd.id = "s2"

    def test_skill_context_defaults(self):
        ctx = SkillContext()
        assert ctx.user_message == ""
        assert ctx.session_id is None
        assert ctx.extra_tools == []
        assert ctx.metadata == {}

    def test_skill_result(self):
        ctx = SkillContext(user_message="hi")
        sr = SkillResult(
            skill_id="s1",
            prompt="be helpful",
            available_tools=["t1"],
            context=ctx,
        )
        assert sr.skill_id == "s1"
        assert sr.context is ctx


# ===========================================================================
# Integration: ToolRegistry + SkillRegistry
# ===========================================================================

class TestIntegration:

    @pytest.mark.asyncio
    async def test_builtin_tools_callable_via_registry(self, registry: ToolRegistry):
        register_builtin_tools(registry)

        result = await registry.call("calculator", operation="add", a=10, b=20)
        assert result == 30.0

    @pytest.mark.asyncio
    async def test_builtin_datetime_callable(self, registry: ToolRegistry):
        register_builtin_tools(registry)

        result = await registry.call("datetime_now", tz="UTC")
        assert "iso" in result
        assert result["tz"] == "UTC"

    def test_skill_validates_against_tool_registry(self):
        """Skill loading fails if referenced tool is not in ToolRegistry."""
        empty_reg = ToolRegistry()
        sr = SkillRegistry(tools=empty_reg)

        # Create a temp yaml that references a tool not registered
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("id: broken\nprompt: p.md\ntools:\n  - missing_tool\n")
            f.flush()
            with pytest.raises(AppError) as exc_info:
                sr.load_from_yaml(f.name)
            assert exc_info.value.code == 7002

    @pytest.mark.asyncio
    async def test_full_flow_register_load_run(self, tmp_path: Path):
        """End-to-end: register tools → load skill → run skill."""
        reg = ToolRegistry()
        register_builtin_tools(reg)

        # Create skill yaml
        yaml_content = """\
id: e2e_skill
description: "E2E test"
prompt: prompts/skills/e2e.md
tools:
  - calculator
execution: fixed
"""
        skill_file = tmp_path / "e2e.yaml"
        skill_file.write_text(yaml_content, encoding="utf-8")

        sr = SkillRegistry(tools=reg)
        sr.load_from_yaml(str(skill_file))

        ctx = SkillContext(user_message="compute 2+3")
        result = await sr.run("e2e_skill", ctx)
        assert result.skill_id == "e2e_skill"
        assert result.available_tools == ["calculator"]
        assert result.context.user_message == "compute 2+3"
