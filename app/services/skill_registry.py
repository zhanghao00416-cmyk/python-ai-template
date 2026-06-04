"""Skill Registry — loads and manages composable skills from YAML declarations.

Implements TOOLS_MCP_SPEC §3: SkillRegistry + SkillDefinition.

A Skill bundles a prompt + bound tools + optional KB scope + constraints
into a reusable capability unit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from app.core.errors import (
    ERROR_CODE_AGENT_TOOL_NOT_FOUND,
    ERROR_CODE_VALIDATION,
    AppError,
    make_error,
)
from app.core.logging import get_logger
from app.tools.registry import ToolRegistry

logger = get_logger("services.skill_registry")


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class SkillDefinition:
    """Immutable metadata for a loaded skill."""

    id: str
    description: str
    prompt_path: str
    tools: list[str]
    kb_scope: dict[str, Any] | None = None
    constraints: dict[str, Any] | None = None
    execution: str = "fixed"  # "fixed" | "llm_select"


@dataclass(slots=True)
class SkillContext:
    """Runtime context passed to a skill during execution."""

    user_message: str = ""
    session_id: str | None = None
    extra_tools: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SkillResult:
    """Outcome of a skill execution."""

    skill_id: str
    prompt: str
    available_tools: list[str]
    context: SkillContext


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class SkillRegistry:
    """Loads skill YAML files and validates tool references against ToolRegistry."""

    def __init__(self, tools: ToolRegistry) -> None:
        self._skills: dict[str, SkillDefinition] = {}
        self._tools = tools

    # -- loading -------------------------------------------------------------

    def load_from_yaml(self, path: str) -> SkillDefinition:
        """Load a skill YAML declaration and validate tool references.

        Raises VALIDATION_ERROR if the file is missing or malformed.
        Raises AGENT_TOOL_NOT_FOUND if a referenced tool is not registered.
        """
        file_path = Path(path)
        if not file_path.exists():
            raise make_error(
                ERROR_CODE_VALIDATION,
                f"Skill file not found: {path}",
            )

        with open(file_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not data or not isinstance(data, dict):
            raise make_error(
                ERROR_CODE_VALIDATION,
                f"Invalid skill YAML: {path}",
            )

        # Validate required fields
        skill_id = data.get("id")
        if not skill_id:
            raise make_error(
                ERROR_CODE_VALIDATION,
                f"Skill YAML missing required field 'id': {path}",
            )

        prompt_path = data.get("prompt", "")
        if not prompt_path:
            raise make_error(
                ERROR_CODE_VALIDATION,
                f"Skill '{skill_id}' missing required field 'prompt'",
            )

        tools_list = data.get("tools", [])
        if not isinstance(tools_list, list):
            raise make_error(
                ERROR_CODE_VALIDATION,
                f"Skill '{skill_id}' field 'tools' must be a list",
            )

        # Validate tool references exist in ToolRegistry
        for tool_name in tools_list:
            if not self._tools.has(tool_name):
                raise make_error(
                    ERROR_CODE_AGENT_TOOL_NOT_FOUND,
                    f"Skill '{skill_id}' references unregistered tool '{tool_name}'",
                )

        skill_def = SkillDefinition(
            id=skill_id,
            description=data.get("description", ""),
            prompt_path=prompt_path,
            tools=tools_list,
            kb_scope=data.get("kb_scope"),
            constraints=data.get("constraints"),
            execution=data.get("execution", "fixed"),
        )

        self._skills[skill_def.id] = skill_def
        logger.info("skill_registry.loaded", skill_id=skill_def.id, tools=tools_list)
        return skill_def

    # -- read ----------------------------------------------------------------

    def get(self, skill_id: str) -> SkillDefinition:
        """Retrieve a skill by id. Raises AGENT_TOOL_NOT_FOUND if missing."""
        try:
            return self._skills[skill_id]
        except KeyError:
            raise make_error(
                ERROR_CODE_AGENT_TOOL_NOT_FOUND,
                f"Skill '{skill_id}' not registered",
            )

    def list_skills(self) -> list[SkillDefinition]:
        """List all registered skills."""
        return list(self._skills.values())

    def has(self, skill_id: str) -> bool:
        """Check whether a skill is registered (without raising)."""
        return skill_id in self._skills

    # -- execution -----------------------------------------------------------

    async def run(self, skill_id: str, context: SkillContext) -> SkillResult:
        """Execute a skill: resolve prompt → compute tool set → return result.

        The actual LLM invocation is handled by the Agent engine (F11+).
        This method prepares the execution context.
        """
        skill = self.get(skill_id)

        # Resolve prompt content from file
        prompt_content = await self._load_prompt(skill.prompt_path)

        # Compute visible capability set: skill_tools ∪ extra_tools
        available_tools = list(skill.tools)
        for extra in context.extra_tools:
            if extra not in available_tools:
                available_tools.append(extra)

        # Detect tool conflicts (skill tool shadowed by extra tool)
        self._check_tool_conflicts(skill, context.extra_tools)

        return SkillResult(
            skill_id=skill_id,
            prompt=prompt_content,
            available_tools=available_tools,
            context=context,
        )

    # -- internals -----------------------------------------------------------

    async def _load_prompt(self, prompt_path: str) -> str:
        """Read prompt file content. Returns placeholder if file missing."""
        file_path = Path(prompt_path)
        if not file_path.exists():
            logger.warning("skill_registry.prompt_missing", path=prompt_path)
            return f"[Prompt file not found: {prompt_path}]"

        return file_path.read_text(encoding="utf-8")

    def _check_tool_conflicts(
        self, skill: SkillDefinition, extra_tools: list[str]
    ) -> None:
        """Warn if extra_tools overlap with skill's bound tools."""
        overlap = set(skill.tools) & set(extra_tools)
        if overlap:
            logger.warning(
                "skill_registry.tool_conflict",
                skill_id=skill.id,
                overlapping=sorted(overlap),
            )

    # -- lifecycle -----------------------------------------------------------

    def clear(self) -> None:
        """Remove all loaded skills."""
        self._skills.clear()


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_instance: SkillRegistry | None = None


def get_skill_registry() -> SkillRegistry | None:
    """Get the global SkillRegistry singleton (may be None before bootstrap)."""
    return _instance


def set_skill_registry(registry: SkillRegistry) -> None:
    """Set the global SkillRegistry singleton (called by bootstrap)."""
    global _instance
    _instance = registry


def reset_skill_registry() -> None:
    """Reset the singleton (for tests only)."""
    global _instance
    if _instance is not None:
        _instance.clear()
    _instance = None
