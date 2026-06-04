"""BaseAgent ABC — abstract execution engine for all agent types.

Implements AGENT_SPEC §Agent Base Class.
Provides: state machine lifecycle, tool dispatch via ToolRegistry,
trajectory recording, and the ``run()`` template method.

Dependency: app/agent/state.py, app/agent/trajectory.py, app/tools/registry.py
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.agent.state import AgentState, transition
from app.agent.trajectory import AgentResult, ToolCall, TokenUsage, TrajectoryEntry
from app.core.errors import (
    ERROR_CODE_AGENT_EXECUTION_FAILED,
    ERROR_CODE_AGENT_MAX_ITERATIONS,
    ERROR_CODE_AGENT_TOOL_NOT_FOUND,
    AppError,
    make_error,
)
from app.core.logging import get_logger
from app.tools.registry import ToolRegistry

logger = get_logger("agent.base")


class BaseAgent(ABC):
    """Abstract base for all agent execution engines.

    Sub-classes must implement :meth:`think` (LLM reasoning step).
    The :meth:`run` template orchestrates the full ReAct lifecycle.
    """

    def __init__(
        self,
        name: str,
        *,
        tool_registry: ToolRegistry,
        max_iterations: int = 10,
        tools: list[str] | None = None,
        agent_type: str = "react",
    ) -> None:
        self.name = name
        self.state: AgentState = AgentState.IDLE
        self.max_iterations = max_iterations
        self.tools: list[str] = tools or []
        self.agent_type = agent_type

        self._tool_registry = tool_registry
        self._trajectory: list[TrajectoryEntry] = []
        self._step_counter: int = 0
        self._total_tokens = TokenUsage()

    # -- public API -----------------------------------------------------------

    async def run(self, user_input: str, context: dict[str, Any] | None = None) -> AgentResult:
        """Execute the full agent loop (template method).

        Sub-classes override ``_run_loop`` for engine-specific behaviour.
        """
        self._reset()
        self._set_state(AgentState.THINKING)

        try:
            result = await self._run_loop(user_input, context or {})
            return result
        except AppError:
            self._set_state(AgentState.ERROR)
            raise
        except Exception as exc:
            self._set_state(AgentState.ERROR)
            logger.error(
                "agent.run.unhandled",
                agent_name=self.name,
                error=str(exc),
            )
            raise make_error(
                ERROR_CODE_AGENT_EXECUTION_FAILED,
                f"Agent '{self.name}' execution failed: {exc}",
            ) from exc

    @abstractmethod
    async def _run_loop(self, user_input: str, context: dict[str, Any]) -> AgentResult:
        """Engine-specific execution loop. Must be implemented by sub-class."""

    # -- think / act / observe ------------------------------------------------

    @abstractmethod
    async def think(
        self,
        user_input: str,
        history: list[TrajectoryEntry],
        context: dict[str, Any],
    ) -> tuple[str, ToolCall | None, TokenUsage]:
        """LLM reasoning step.

        Returns:
            (thought_text, tool_call_or_none, token_usage)

        If ``tool_call`` is ``None`` the LLM produced a final answer
        (stored in ``thought_text``).
        """

    async def act(self, tool_call: ToolCall) -> Any:
        """Execute a tool via the registry during the ACTING phase."""
        self._set_state(AgentState.ACTING)

        if not self._tool_registry.has(tool_call.tool):
            logger.warning(
                "agent.act.tool_not_found",
                agent_name=self.name,
                tool=tool_call.tool,
            )
            # Per AGENT_SPEC: report to LLM and continue ReAct
            return {
                "error": f"Tool '{tool_call.tool}' not registered",
                "error_code": ERROR_CODE_AGENT_TOOL_NOT_FOUND,
            }

        try:
            result = await self._tool_registry.call(tool_call.tool, **tool_call.input)
            return result
        except AppError:
            raise
        except Exception as exc:
            logger.error(
                "agent.act.tool_failed",
                agent_name=self.name,
                tool=tool_call.tool,
                error=str(exc),
            )
            return {"error": str(exc)}

    def observe(self, result: Any) -> str:
        """Format a tool result for the next reasoning step."""
        self._set_state(AgentState.OBSERVING)
        if isinstance(result, str):
            return result
        if isinstance(result, dict):
            if "error" in result:
                return f"Tool error: {result['error']}"
            return str(result)
        return str(result)

    # -- iteration guard ------------------------------------------------------

    def should_continue(self, iteration: int) -> bool:
        """Return True if the agent may continue; False if max_iterations hit."""
        if iteration >= self.max_iterations:
            return False
        if self.state in (AgentState.DONE, AgentState.ERROR):
            return False
        return True

    # -- state management -----------------------------------------------------

    def _set_state(self, target: AgentState) -> None:
        """Validate and apply a state transition."""
        self.state = transition(self.state, target)

    # -- trajectory helpers ---------------------------------------------------

    def _record(
        self,
        state: AgentState,
        *,
        thought: str | None = None,
        action: ToolCall | None = None,
        observation: Any | None = None,
        token_usage: TokenUsage | None = None,
    ) -> TrajectoryEntry:
        """Append a TrajectoryEntry and return it."""
        self._step_counter += 1
        entry = TrajectoryEntry(
            agent_name=self.name,
            step_index=self._step_counter,
            state=state.value,
            thought=thought,
            action=action,
            observation=observation,
            token_usage=token_usage,
        )
        self._trajectory.append(entry)
        return entry

    def _accumulate_tokens(self, usage: TokenUsage) -> None:
        self._total_tokens = TokenUsage(
            input_tokens=self._total_tokens.input_tokens + usage.input_tokens,
            output_tokens=self._total_tokens.output_tokens + usage.output_tokens,
        )

    def _reset(self) -> None:
        """Reset agent state for a fresh run."""
        self.state = AgentState.IDLE
        self._trajectory.clear()
        self._step_counter = 0
        self._total_tokens = TokenUsage()

    def _build_result(self, content: str) -> AgentResult:
        return AgentResult(
            content=content,
            agent_name=self.name,
            agent_type=self.agent_type,
            trajectory=list(self._trajectory),
            total_token_usage=self._total_tokens,
        )
