"""Agent orchestration service — business layer for agent execution.

Creates the appropriate agent engine (ReactAgent), executes it,
and persists trajectory records via AgentTrajectoryRepo.

Dependency: app/agent/ (engine), app/tools/registry.py,
            app/domain/agent_orchestration/repo.py
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
import yaml

from app.agent.base import BaseAgent
from app.agent.orchestrator import OrchestratorAgent
from app.agent.react import ReactAgent
from app.agent.trajectory import AgentResult, TrajectoryEntry
from app.core.errors import (
    ERROR_CODE_AGENT_EXECUTION_FAILED,
    ERROR_CODE_SERVICE_UNAVAILABLE,
    make_error,
)
from app.core.logging import get_logger
from app.domain.agent_orchestration.repo import AgentTrajectoryRepo
from app.schemas.agent import (
    AgentRunResponse,
    AgentType,
    AgentUsageDetail,
    TrajectoryDetail,
    TrajectoryListItem,
    TrajectoryStepDetail,
)
from app.tools.registry import ToolRegistry

logger = get_logger("domain.agent_orchestration.service")


def _load_agent_configs() -> dict[str, dict[str, Any]]:
    """Load agent role configs from configs/agents.yaml."""
    try:
        from pathlib import Path

        config_path = Path("configs/agents.yaml")
        if config_path.is_file():
            with open(config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            return data.get("agents", {})
    except Exception as exc:
        logger.warning("agent_orchestration.config_load_failed", error=str(exc))
    return {}


class AgentOrchestrationService:
    """Business service that bridges agent/ engine with persistence."""

    def __init__(
        self,
        repo: AgentTrajectoryRepo,
        tool_registry: ToolRegistry,
    ) -> None:
        self._repo = repo
        self._tool_registry = tool_registry
        self._agent_configs = _load_agent_configs()

    async def run_agent(
        self,
        user_id: str,
        session_id: str,
        query: str,
        *,
        agent_type: str = "react",
        agent_name: str | None = None,
        tools: list[str] | None = None,
        skills: list[str] | None = None,
        max_steps: int = 10,
        model_override: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AgentRunResponse:
        """Execute an agent run and persist trajectory."""

        # Resolve agent config
        role_name = agent_name or "general_chat"
        agent_cfg = self._agent_configs.get(role_name, {})

        effective_tools = tools if tools is not None else agent_cfg.get("tools", [])
        effective_max_steps = max_steps or agent_cfg.get("max_iterations", 10)

        # Create engine
        agent = self._create_engine(
            agent_type=agent_type,
            name=role_name,
            tools=effective_tools,
            max_iterations=effective_max_steps,
        )

        # Execute
        context: dict[str, Any] = {
            "user_id": user_id,
            "session_id": session_id,
            "model_override": model_override,
        }
        if metadata:
            context.update(metadata)

        try:
            result = await agent.run(query, context)
        except Exception as exc:
            logger.error(
                "agent_orchestration.run_failed",
                agent_name=role_name,
                error=str(exc),
            )
            raise

        # Persist trajectory
        task_id = str(uuid.uuid4())
        await self._persist_trajectory(
            session_id=session_id,
            task_id=task_id,
            result=result,
        )

        # Build response
        return self._build_response(task_id=task_id, result=result)

    async def list_trajectories(
        self,
        session_id: str | None = None,
        agent_name: str | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[TrajectoryListItem], int]:
        """List trajectory summaries."""
        from app.infra.database import Pagination

        sid = uuid.UUID(session_id) if session_id else None
        pagination = Pagination(offset=offset, limit=limit)
        entries, total = await self._repo.list_by_session_grouped(
            session_id=sid,
            agent_name=agent_name,
            pagination=pagination,
        )

        # Group by (session_id, agent_name) to build task-level summaries
        groups: dict[str, list] = {}
        for entry in entries:
            key = f"{entry.session_id}:{entry.agent_name}"
            groups.setdefault(key, []).append(entry)

        items: list[TrajectoryListItem] = []
        for key, group_entries in groups.items():
            first = group_entries[0]
            last = group_entries[-1]
            status = "completed" if last.state in ("DONE", "IDLE") else last.state.lower()
            items.append(TrajectoryListItem(
                task_id=str(first.session_id),
                session_id=str(first.session_id),
                agent_name=first.agent_name,
                agent_type="react",
                step_count=len(group_entries),
                status=status,
                created_at=first.created_at.isoformat() if first.created_at else "",
            ))

        return items, total

    async def get_trajectory_detail(self, task_id: str) -> TrajectoryDetail | None:
        """Get full trajectory detail by session_id (task_id maps to session_id)."""
        from app.infra.database import Pagination

        try:
            sid = uuid.UUID(task_id)
        except (ValueError, TypeError):
            return None

        entries, _ = await self._repo.list_by_session(
            session_id=sid,
            pagination=Pagination(offset=0, limit=100, sort_by="step_index", sort_order="asc"),
        )
        if not entries:
            return None

        steps = [
            TrajectoryStepDetail(
                step_index=e.step_index,
                state=e.state,
                thought=e.thought,
                action=e.action,
                observation=e.observation,
                token_usage=e.token_usage,
                created_at=e.created_at.isoformat() if e.created_at else None,
            )
            for e in entries
        ]

        total_input = sum((e.token_usage or {}).get("input_tokens", 0) for e in entries)
        total_output = sum((e.token_usage or {}).get("output_tokens", 0) for e in entries)

        first = entries[0]
        last = entries[-1]
        status = "completed" if last.state in ("DONE", "IDLE") else last.state.lower()

        return TrajectoryDetail(
            task_id=task_id,
            session_id=str(first.session_id),
            agent_name=first.agent_name,
            agent_type="react",
            status=status,
            steps=steps,
            total_token_usage=AgentUsageDetail(
                input_tokens=total_input,
                output_tokens=total_output,
            ),
            created_at=first.created_at.isoformat() if first.created_at else "",
            completed_at=last.created_at.isoformat() if last.created_at else None,
        )

    # -- private helpers ------------------------------------------------------

    def _create_engine(
        self,
        agent_type: str,
        name: str,
        tools: list[str],
        max_iterations: int,
    ) -> BaseAgent:
        """Factory: create the appropriate agent engine."""
        if agent_type == "react":
            return ReactAgent(
                name=name,
                tool_registry=self._tool_registry,
                max_iterations=max_iterations,
                tools=tools,
            )
        if agent_type == "orchestrator":
            # Build sub-agents from configs/agents.yaml orchestrator section
            orch_cfg = self._agent_configs.get("__orchestrator__", {})
            # Fallback: read orchestrator config from top-level agents.yaml
            if not orch_cfg:
                orch_cfg = self._load_orchestrator_config()
            max_sub = orch_cfg.get("max_sub_agents", 5)
            sub_agents = self._build_sub_agents(tools, max_iterations)
            return OrchestratorAgent(
                name=name,
                tool_registry=self._tool_registry,
                max_iterations=max_iterations,
                tools=tools,
                sub_agents=sub_agents,
                max_sub_agents=max_sub,
            )
        # workflow — placeholder for F13
        logger.warning(
            "agent_orchestration.engine_fallback",
            agent_type=agent_type,
            fallback="react",
        )
        return ReactAgent(
            name=name,
            tool_registry=self._tool_registry,
            max_iterations=max_iterations,
            tools=tools,
        )

    async def _persist_trajectory(
        self,
        session_id: str,
        task_id: str,
        result: AgentResult,
    ) -> None:
        """Persist trajectory entries to DB (best-effort)."""
        try:
            sid = uuid.UUID(session_id)
        except (ValueError, TypeError):
            sid = uuid.uuid4()

        entries_data = []
        for entry in result.trajectory:
            entries_data.append({
                "step_index": entry.step_index,
                "state": entry.state,
                "thought": entry.thought,
                "action": entry.action_to_dict(),
                "observation": entry.observation_to_dict(),
                "token_usage": entry.token_usage_to_dict(),
            })

        if entries_data:
            try:
                await self._repo.save_trajectory_entries(
                    session_id=sid,
                    agent_name=result.agent_name,
                    entries=entries_data,
                )
                logger.info(
                    "agent_orchestration.trajectory_saved",
                    task_id=task_id,
                    entries=len(entries_data),
                )
            except Exception as exc:
                logger.warning(
                    "agent_orchestration.trajectory_save_failed",
                    task_id=task_id,
                    error=str(exc),
                )

    def _build_sub_agents(
        self,
        tools: list[str],
        max_iterations: int,
    ) -> dict[str, BaseAgent]:
        """Create sub-agent engines from agents.yaml definitions."""
        sub_agents: dict[str, BaseAgent] = {}
        for agent_name, cfg in self._agent_configs.items():
            # Skip orchestrator meta keys and general_chat
            if agent_name.startswith("__") or agent_name == "general_chat":
                continue
            agent_tools = cfg.get("tools", tools)
            sub_agents[agent_name] = ReactAgent(
                name=agent_name,
                tool_registry=self._tool_registry,
                max_iterations=cfg.get("max_iterations", max_iterations),
                tools=agent_tools,
            )
        return sub_agents

    @staticmethod
    def _load_orchestrator_config() -> dict[str, Any]:
        """Load orchestrator config from configs/agents.yaml orchestrator section."""
        try:
            from pathlib import Path

            config_path = Path("configs/agents.yaml")
            if config_path.is_file():
                with open(config_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                return data.get("orchestrator", {})
        except Exception:
            pass
        return {}

    def _build_response(self, task_id: str, result: AgentResult) -> AgentRunResponse:
        """Convert AgentResult to API response schema."""
        steps = [
            TrajectoryStepDetail(
                step_index=e.step_index,
                state=e.state,
                thought=e.thought,
                action=e.action_to_dict(),
                observation=e.observation_to_dict(),
                token_usage=e.token_usage_to_dict(),
                created_at=e.timestamp.isoformat() if e.timestamp else None,
            )
            for e in result.trajectory
        ]

        return AgentRunResponse(
            task_id=task_id,
            content=result.content,
            citations=[],
            trajectory=steps,
            usage=AgentUsageDetail(
                input_tokens=result.total_token_usage.input_tokens,
                output_tokens=result.total_token_usage.output_tokens,
            ),
        )
