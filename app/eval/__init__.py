"""Evaluation framework — dialogue quality + agent trajectory evaluation.

Public API:
- EvalRunner        — batch evaluation executor
- metrics           — dialogue quality algorithms
- trajectory_eval   — trajectory analysis algorithms
"""

from __future__ import annotations

from app.eval.metrics import (
    citation_accuracy,
    dialogue_turn_balance,
    response_conciseness,
    response_relevance,
)
from app.eval.runner import EvalRunner
from app.eval.trajectory_eval import (
    loop_detection,
    state_transition_validity,
    step_efficiency,
    tool_call_success_rate,
    trajectory_completeness,
)

__all__ = [
    "EvalRunner",
    "citation_accuracy",
    "dialogue_turn_balance",
    "loop_detection",
    "response_conciseness",
    "response_relevance",
    "state_transition_validity",
    "step_efficiency",
    "tool_call_success_rate",
    "trajectory_completeness",
]
