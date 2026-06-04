"""Workflow engine package — StateGraph DAG executor + registry.

Public API:

* :class:`StateGraph` — DAG builder (nodes + edges + conditional edges)
* :class:`Edge` — unconditional edge dataclass
* :class:`ConditionalEdge` — conditional edge dataclass
* :class:`NodeExecutionResult` — per-node execution result
* :class:`WorkflowEngine` — DAG executor
* :class:`WorkflowRegistry` — central workflow store
"""

from app.workflow.engine import (
    ConditionalEdge,
    Edge,
    NodeExecutionResult,
    StateGraph,
    WorkflowEngine,
)
from app.workflow.registry import (
    WorkflowRegistry,
    get_workflow_registry,
    reset_workflow_registry,
)

__all__ = [
    "ConditionalEdge",
    "Edge",
    "NodeExecutionResult",
    "StateGraph",
    "WorkflowEngine",
    "WorkflowRegistry",
    "get_workflow_registry",
    "reset_workflow_registry",
]
