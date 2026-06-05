"""ReactAgent — ReAct (Reasoning + Acting) loop engine.

Implements AGENT_SPEC §ReAct Loop:
  1. THINKING: LLM generates thought + optional tool call
  2. ACTING: execute tool via registry
  3. OBSERVING: format tool result
  4. Repeat until final answer or max_iterations

Dependency: app/agent/base.py, app/agent/state.py, app/agent/trajectory.py
"""

from __future__ import annotations

import time
from typing import Any

from app.agent.base import BaseAgent
from app.agent.state import AgentState
from app.agent.trajectory import AgentResult, TokenUsage, ToolCall, TrajectoryEntry
from app.core.errors import (
    ERROR_CODE_AGENT_MAX_ITERATIONS,
    make_error,
)
from app.core.logging import get_logger
from app.tools.registry import ToolRegistry

logger = get_logger("agent.react")


class ReactAgent(BaseAgent):
    """ReAct execution engine.

    The core loop:
      THINKING → (ACTING → OBSERVING)* → DONE

    The LLM is called via the abstract ``think()`` method, which must be
    supplied by the domain layer (or via constructor injection).
    """

    def __init__(
        self,
        name: str,
        *,
        tool_registry: ToolRegistry,
        max_iterations: int = 10,
        tools: list[str] | None = None,
        think_fn: Any | None = None,
    ) -> None:
        super().__init__(
            name=name,
            tool_registry=tool_registry,
            max_iterations=max_iterations,
            tools=tools,
            agent_type="react",
        )
        # Optional injected think function for non-LLM usage / testing.
        # Signature: async (user_input, history, context) -> (thought, tool_call, usage)
        self._think_fn = think_fn

    async def think(
        self,
        user_input: str,
        history: list[TrajectoryEntry],
        context: dict[str, Any],
    ) -> tuple[str, ToolCall | None, TokenUsage]:
        """Delegate to the injected think_fn or return a no-op default."""
        if self._think_fn is not None:
            return await self._think_fn(user_input, history, context)
        # Fallback: immediately produce a final answer (for testing without LLM)
        return (f"Echo: {user_input}", None, TokenUsage())

    async def _run_loop(self, user_input: str, context: dict[str, Any]) -> AgentResult:
        """Execute the ReAct loop: THINKING → ACTING → OBSERVING → ..."""
        current_input = user_input
        iteration = 0

        while self.should_continue(iteration):
            iteration += 1
            logger.debug(
                "agent.react.iteration",
                agent_name=self.name,
                iteration=iteration,
                max_iterations=self.max_iterations,
            )

            step_start = time.perf_counter()

            # --- THINKING ---
            self._set_state(AgentState.THINKING)
            thought, tool_call, token_usage = await self.think(
                current_input, list(self._trajectory), context,
            )
            self._accumulate_tokens(token_usage)
            self._record(
                AgentState.THINKING,
                thought=thought,
                token_usage=token_usage,
            )

            # --- Final answer (no tool call) ---
            if tool_call is None:
                self._set_state(AgentState.DONE)
                self._record(AgentState.DONE, thought=thought)
                duration = time.perf_counter() - step_start
                self._record_step(duration)
                logger.info(
                    "agent.react.done",
                    agent_name=self.name,
                    iterations=iteration,
                    total_input_tokens=self._total_tokens.input_tokens,
                    total_output_tokens=self._total_tokens.output_tokens,
                )
                return self._build_result(content=thought)

            # --- ACTING ---
            self._record(AgentState.ACTING, action=tool_call)
            tool_result = await self.act(tool_call)

            # --- OBSERVING ---
            observation_text = self.observe(tool_result)
            self._record(
                AgentState.OBSERVING,
                observation=tool_result,
            )

            duration = time.perf_counter() - step_start
            self._record_step(duration)

            # Feed observation back as next input
            current_input = observation_text

        # Max iterations reached
        logger.warning(
            "agent.react.max_iterations",
            agent_name=self.name,
            max_iterations=self.max_iterations,
        )
        # Transition to THINKING first (valid from any non-terminal state),
        # then to DONE.
        self._set_state(AgentState.THINKING)
        self._set_state(AgentState.DONE)
        self._record(
            AgentState.DONE,
            thought=f"Reached maximum iterations ({self.max_iterations}). Returning partial result.",
        )
        partial = self._last_thought() or "No final answer produced."
        result = self._build_result(content=partial)
        # Attach max-iterations marker without raising (spec: return partial result)
        result.task_id = f"max_iterations_{self.max_iterations}"
        return result

    def _last_thought(self) -> str | None:
        """Return the most recent thought text from trajectory."""
        for entry in reversed(self._trajectory):
            if entry.thought is not None:
                return entry.thought
        return None
