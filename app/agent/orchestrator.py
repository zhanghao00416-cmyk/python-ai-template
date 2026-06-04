"""OrchestratorAgent — multi-agent coordination engine.

Implements AGENT_SPEC §Multi-Agent Coordination:
  1. plan()    — decompose task into sub-tasks
  2. delegate() — assign sub-tasks to sub-agents
  3. synthesize() — collect and synthesise results

Also provides DebateStrategy for iterative propose/critique/revise cycles.

Dependency: app/agent/base.py, app/agent/state.py, app/agent/trajectory.py,
            app/agent/react.py
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.agent.base import BaseAgent
from app.agent.react import ReactAgent
from app.agent.state import AgentState
from app.agent.trajectory import AgentResult, TokenUsage, ToolCall, TrajectoryEntry
from app.core.errors import (
    ERROR_CODE_AGENT_ORCHESTRATION_FAILED,
    make_error,
)
from app.core.logging import get_logger
from app.tools.registry import ToolRegistry

logger = get_logger("agent.orchestrator")


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class SubTask:
    """A unit of work delegated to a sub-agent."""

    task_id: str
    description: str
    agent_name: str
    context: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SubTaskResult:
    """Result from a single sub-agent delegation."""

    task_id: str
    agent_name: str
    content: str
    success: bool
    token_usage: TokenUsage = field(default_factory=TokenUsage)
    trajectory: list[TrajectoryEntry] = field(default_factory=list)


# ---------------------------------------------------------------------------
# DebateStrategy
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class DebateStrategy:
    """Iterative propose → critique → revise collaboration strategy.

    Implements AGENT_SPEC §Debate Strategy:
      1. Agent A proposes a solution
      2. Agent B critiques the solution
      3. Agent A revises based on critique
      4. Repeat for N rounds or until consensus
    """

    rounds: int = 3
    consensus_threshold: float = 0.8

    async def execute(
        self,
        proposer: BaseAgent,
        critic: BaseAgent,
        task_description: str,
    ) -> DebateResult:
        """Run the debate loop between proposer and critic."""
        current_proposal = task_description
        history: list[DebateRound] = []

        for round_idx in range(self.rounds):
            # Proposer generates / refines proposal
            prop_result = await proposer.run(current_proposal)
            proposal_text = prop_result.content

            # Critic evaluates the proposal
            critique_input = (
                f"Please critique the following proposal and provide a score "
                f"(0.0-1.0) on a line like 'SCORE: X.X':\n\n{proposal_text}"
            )
            crit_result = await critic.run(critique_input)
            critique_text = crit_result.content

            # Parse consensus score from critic output
            score = self._parse_score(critique_text)
            history.append(DebateRound(
                round_index=round_idx + 1,
                proposal=proposal_text,
                critique=critique_text,
                score=score,
            ))

            logger.debug(
                "orchestrator.debate.round",
                round=round_idx + 1,
                score=score,
                threshold=self.consensus_threshold,
            )

            if score >= self.consensus_threshold:
                return DebateResult(
                    final_answer=proposal_text,
                    rounds_completed=round_idx + 1,
                    consensus_reached=True,
                    history=history,
                    total_token_usage=TokenUsage(
                        input_tokens=(
                            prop_result.total_token_usage.input_tokens
                            + crit_result.total_token_usage.input_tokens
                        ),
                        output_tokens=(
                            prop_result.total_token_usage.output_tokens
                            + crit_result.total_token_usage.output_tokens
                        ),
                    ),
                )

            # Feed critique back as next proposal input
            current_proposal = (
                f"Original task: {task_description}\n\n"
                f"Previous proposal: {proposal_text}\n\n"
                f"Critique: {critique_text}\n\n"
                f"Please revise the proposal based on the critique."
            )

        # Max rounds reached without consensus
        last_proposal = history[-1].proposal if history else task_description
        return DebateResult(
            final_answer=last_proposal,
            rounds_completed=self.rounds,
            consensus_reached=False,
            history=history,
            total_token_usage=TokenUsage(),
        )

    @staticmethod
    def _parse_score(text: str) -> float:
        """Extract a score (0.0-1.0) from critique text."""
        import re

        match = re.search(r"SCORE:\s*(\d+\.?\d*)", text, re.IGNORECASE)
        if match:
            try:
                score = float(match.group(1))
                return max(0.0, min(1.0, score))
            except ValueError:
                pass
        return 0.5  # Default: no consensus


@dataclass(frozen=True, slots=True)
class DebateRound:
    """One round in a debate."""

    round_index: int
    proposal: str
    critique: str
    score: float


@dataclass(frozen=True, slots=True)
class DebateResult:
    """Final result of a debate execution."""

    final_answer: str
    rounds_completed: int
    consensus_reached: bool
    history: list[DebateRound] = field(default_factory=list)
    total_token_usage: TokenUsage = field(default_factory=TokenUsage)


# ---------------------------------------------------------------------------
# OrchestratorAgent
# ---------------------------------------------------------------------------

class OrchestratorAgent(BaseAgent):
    """Multi-agent orchestrator — coordinates sub-agents to solve complex tasks.

    Implements AGENT_SPEC §Orchestrator Mode:
      1. Decompose task into sub-tasks (plan)
      2. Assign sub-tasks to specialised agents (delegate)
      3. Collect and synthesise results (synthesize)

    Sub-agents communicate only through the orchestrator (no direct
    agent-to-agent communication). Each sub-agent has its own independent
    trajectory record.
    """

    def __init__(
        self,
        name: str,
        *,
        tool_registry: ToolRegistry,
        max_iterations: int = 10,
        tools: list[str] | None = None,
        sub_agents: dict[str, BaseAgent] | None = None,
        max_sub_agents: int = 5,
        think_fn: Any | None = None,
    ) -> None:
        super().__init__(
            name=name,
            tool_registry=tool_registry,
            max_iterations=max_iterations,
            tools=tools,
            agent_type="orchestrator",
        )
        self._sub_agents: dict[str, BaseAgent] = sub_agents or {}
        self._max_sub_agents = max_sub_agents
        self._think_fn = think_fn

    # -- sub-agent management ------------------------------------------------

    def add_sub_agent(self, agent_name: str, agent: BaseAgent) -> None:
        """Register a sub-agent for delegation."""
        if len(self._sub_agents) >= self._max_sub_agents:
            logger.warning(
                "orchestrator.sub_agent_limit",
                max=self._max_sub_agents,
                requested=agent_name,
            )
            return
        self._sub_agents[agent_name] = agent

    @property
    def sub_agents(self) -> dict[str, BaseAgent]:
        return dict(self._sub_agents)

    # -- think (required by BaseAgent ABC) -----------------------------------

    async def think(
        self,
        user_input: str,
        history: list[TrajectoryEntry],
        context: dict[str, Any],
    ) -> tuple[str, ToolCall | None, TokenUsage]:
        """Delegate to injected think_fn or produce a no-op default."""
        if self._think_fn is not None:
            return await self._think_fn(user_input, history, context)
        return (f"Orchestrator echo: {user_input}", None, TokenUsage())

    # -- plan / delegate / synthesize ----------------------------------------

    async def plan(
        self,
        user_input: str,
        context: dict[str, Any] | None = None,
    ) -> list[SubTask]:
        """Decompose the user input into sub-tasks for delegation.

        Uses the injected think_fn (LLM) to generate a plan, or falls back
        to a simple round-robin distribution across available sub-agents.
        """
        ctx = context or {}

        if self._think_fn is not None:
            # Ask LLM to generate a plan
            plan_prompt = (
                f"Decompose the following task into sub-tasks. "
                f"Available agents: {list(self._sub_agents.keys())}. "
                f"Return a JSON list of objects with 'description' and "
                f"'agent_name' fields.\n\nTask: {user_input}"
            )
            thought, _, token_usage = await self._think_fn(
                plan_prompt, [], ctx,
            )
            sub_tasks = self._parse_plan(thought)
            if sub_tasks:
                self._accumulate_tokens(token_usage)
                return sub_tasks

        # Fallback: assign one sub-task per available sub-agent
        sub_tasks = []
        agent_names = list(self._sub_agents.keys())
        if not agent_names:
            return [SubTask(
                task_id="subtask_1",
                description=user_input,
                agent_name=self.name,
            )]

        for idx, agent_name in enumerate(agent_names):
            sub_tasks.append(SubTask(
                task_id=f"subtask_{idx + 1}",
                description=user_input,
                agent_name=agent_name,
                context=ctx,
            ))

        return sub_tasks

    async def delegate(self, sub_task: SubTask) -> SubTaskResult:
        """Execute a sub-task on the assigned sub-agent."""
        agent = self._sub_agents.get(sub_task.agent_name)
        if agent is None:
            logger.warning(
                "orchestrator.delegate.agent_not_found",
                agent_name=sub_task.agent_name,
                task_id=sub_task.task_id,
            )
            return SubTaskResult(
                task_id=sub_task.task_id,
                agent_name=sub_task.agent_name,
                content=f"Sub-agent '{sub_task.agent_name}' not available",
                success=False,
            )

        try:
            result: AgentResult = await agent.run(
                sub_task.description,
                sub_task.context,
            )
            return SubTaskResult(
                task_id=sub_task.task_id,
                agent_name=sub_task.agent_name,
                content=result.content,
                success=True,
                token_usage=result.total_token_usage,
                trajectory=result.trajectory,
            )
        except Exception as exc:
            logger.error(
                "orchestrator.delegate.failed",
                agent_name=sub_task.agent_name,
                task_id=sub_task.task_id,
                error=str(exc),
            )
            return SubTaskResult(
                task_id=sub_task.task_id,
                agent_name=sub_task.agent_name,
                content=f"Sub-agent failed: {exc}",
                success=False,
            )

    async def synthesize(
        self,
        results: list[SubTaskResult],
        original_input: str = "",
    ) -> str:
        """Synthesise sub-agent results into a final answer.

        If a think_fn (LLM) is available, asks it to synthesise.
        Otherwise, concatenates successful results.
        """
        successful = [r for r in results if r.success]
        failed = [r for r in results if not r.success]

        if self._think_fn is not None and successful:
            synth_prompt = (
                f"Original task: {original_input}\n\n"
                f"Sub-agent results:\n"
            )
            for r in successful:
                synth_prompt += f"- [{r.agent_name}]: {r.content}\n"
            synth_prompt += "\nPlease synthesise these results into a coherent final answer."

            thought, _, token_usage = await self._think_fn(
                synth_prompt, [], {},
            )
            self._accumulate_tokens(token_usage)
            return thought

        # Fallback: concatenate
        parts = []
        for r in successful:
            parts.append(f"[{r.agent_name}]: {r.content}")
        if failed:
            parts.append(
                f"({len(failed)} sub-agent(s) failed: "
                f"{', '.join(r.agent_name for r in failed)})"
            )
        return "\n".join(parts) if parts else "No sub-agent produced results."

    # -- _run_loop (BaseEngine template method) ------------------------------

    async def _run_loop(self, user_input: str, context: dict[str, Any]) -> AgentResult:
        """Full orchestrator lifecycle: plan → delegate → synthesise."""
        iteration = 0

        # --- Record THINKING (planning) ---
        self._set_state(AgentState.THINKING)
        self._record(AgentState.THINKING, thought=f"Planning sub-tasks for: {user_input}")

        # --- Plan ---
        sub_tasks = await self.plan(user_input, context)
        if not sub_tasks:
            self._set_state(AgentState.DONE)
            self._record(AgentState.DONE, thought="No sub-tasks generated.")
            return self._build_result("No sub-tasks could be planned.")

        logger.info(
            "orchestrator.planned",
            agent_name=self.name,
            sub_tasks=len(sub_tasks),
        )

        # --- Delegate (sequential by default per AGENT_SPEC §Concurrency) ---
        results: list[SubTaskResult] = []
        for sub_task in sub_tasks:
            if not self.should_continue(iteration):
                break
            iteration += 1

            # ACTING: delegate to sub-agent
            self._set_state(AgentState.ACTING)
            self._record(
                AgentState.ACTING,
                action=ToolCall(
                    tool=f"delegate:{sub_task.agent_name}",
                    input={"task_id": sub_task.task_id, "description": sub_task.description},
                ),
            )

            result = await self.delegate(sub_task)
            results.append(result)

            # OBSERVING: process sub-agent result
            self._set_state(AgentState.OBSERVING)
            self._record(
                AgentState.OBSERVING,
                observation={
                    "task_id": result.task_id,
                    "agent_name": result.agent_name,
                    "success": result.success,
                    "content_preview": result.content[:200] if result.content else "",
                },
            )

            # Accumulate sub-agent tokens
            self._accumulate_tokens(result.token_usage)

            # Back to THINKING for next delegation or synthesis
            self._set_state(AgentState.THINKING)

        # --- Synthesise ---
        self._set_state(AgentState.THINKING)
        self._record(
            AgentState.THINKING,
            thought=f"Synthesising {len(results)} sub-agent results",
        )

        final_answer = await self.synthesize(results, user_input)

        # --- Done ---
        self._set_state(AgentState.DONE)
        self._record(AgentState.DONE, thought=final_answer)

        logger.info(
            "orchestrator.done",
            agent_name=self.name,
            sub_tasks_total=len(sub_tasks),
            sub_tasks_success=sum(1 for r in results if r.success),
            sub_tasks_failed=sum(1 for r in results if not r.success),
        )

        return self._build_result(content=final_answer)

    # -- helpers -------------------------------------------------------------

    @staticmethod
    def _parse_plan(text: str) -> list[SubTask]:
        """Attempt to parse LLM-generated plan JSON into SubTask list."""
        import json
        import re

        # Try to extract JSON from the text
        json_match = re.search(r"\[[\s\S]*\]", text)
        if not json_match:
            return []

        try:
            items = json.loads(json_match.group())
        except (json.JSONDecodeError, ValueError):
            return []

        sub_tasks = []
        for idx, item in enumerate(items):
            if isinstance(item, dict):
                sub_tasks.append(SubTask(
                    task_id=f"subtask_{idx + 1}",
                    description=str(item.get("description", "")),
                    agent_name=str(item.get("agent_name", "")),
                ))
        return sub_tasks
