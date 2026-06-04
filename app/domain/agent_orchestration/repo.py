"""Agent trajectory repository — persistence layer bridge.

Stores TrajectoryEntry records into the ``agent_trajectories`` PG table
via BaseRepo[AgentTrajectoryModel].

Dependency: F02 (app/infra/database.py BaseRepo), F02 (app/infra/models.py)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.database import BaseRepo, Pagination
from app.infra.models import AgentTrajectoryModel

logger = structlog.get_logger("domain.agent_orchestration.repo")


class AgentTrajectoryRepo(BaseRepo[AgentTrajectoryModel]):
    """Repository for Agent trajectory persistence."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(AgentTrajectoryModel, session)

    async def save_trajectory_entries(
        self,
        session_id: uuid.UUID,
        agent_name: str,
        entries: list[dict],
    ) -> list[AgentTrajectoryModel]:
        """Bulk-insert trajectory entries for one agent run."""
        saved: list[AgentTrajectoryModel] = []
        for entry_data in entries:
            record = await self.create({
                "session_id": session_id,
                "agent_name": agent_name,
                "step_index": entry_data["step_index"],
                "state": entry_data["state"],
                "thought": entry_data.get("thought"),
                "action": entry_data.get("action"),
                "observation": entry_data.get("observation"),
                "token_usage": entry_data.get("token_usage"),
            })
            saved.append(record)
        return saved

    async def list_by_session(
        self,
        session_id: uuid.UUID,
        pagination: Pagination | None = None,
    ) -> tuple[list[AgentTrajectoryModel], int]:
        """List trajectory entries for a session."""
        result = await self.list(
            filters={"session_id": session_id},
            pagination=pagination,
        )
        return list(result.items), result.total

    async def list_by_session_grouped(
        self,
        session_id: uuid.UUID | None = None,
        agent_name: str | None = None,
        pagination: Pagination | None = None,
    ) -> tuple[list[AgentTrajectoryModel], int]:
        """List trajectories with optional session + agent filters."""
        filters: dict = {}
        if session_id is not None:
            filters["session_id"] = session_id
        if agent_name is not None:
            filters["agent_name"] = agent_name
        result = await self.list(
            filters=filters or None,
            pagination=pagination,
        )
        return list(result.items), result.total
