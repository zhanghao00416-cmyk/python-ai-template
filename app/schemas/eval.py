"""Evaluation schemas — data models for eval results.

Pure Pydantic models; no business logic.
Dependency: none.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class EvalDimension(StrEnum):
    """Supported evaluation dimensions."""

    STATE_TRANSITION_VALIDITY = "state_transition_validity"
    TOOL_CALL_SUCCESS_RATE = "tool_call_success_rate"
    LOOP_DETECTION = "loop_detection"
    STEP_EFFICIENCY = "step_efficiency"
    TRAJECTORY_COMPLETENESS = "trajectory_completeness"
    RESPONSE_RELEVANCE = "response_relevance"
    RESPONSE_CONCISENESS = "response_conciseness"
    CITATION_ACCURACY = "citation_accuracy"


class EvalGrade(StrEnum):
    """Qualitative grade for a dimension."""

    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"


# ---------------------------------------------------------------------------
# Score
# ---------------------------------------------------------------------------

class EvalScore(BaseModel):
    """Score for a single evaluation dimension."""

    dimension: EvalDimension = Field(..., description="评估维度")
    score: float = Field(..., ge=0.0, le=1.0, description="0.0-1.0 分数")
    grade: EvalGrade = Field(..., description="定性评级")
    details: dict[str, Any] = Field(default_factory=dict, description="原始指标")
    issues: list[str] = Field(default_factory=list, description="发现的问题")


# ---------------------------------------------------------------------------
# Trajectory evaluation
# ---------------------------------------------------------------------------

class TrajectoryEvalResult(BaseModel):
    """Result of evaluating a single Agent trajectory."""

    agent_name: str = Field(default="", description="Agent 名称")
    agent_type: str = Field(default="", description="Agent 类型")
    total_steps: int = Field(default=0, description="总步数")
    overall_score: float = Field(default=0.0, ge=0.0, le=1.0, description="综合分数")
    grade: EvalGrade = Field(default=EvalGrade.POOR, description="综合评级")
    scores: list[EvalScore] = Field(default_factory=list, description="各维度得分")
    summary: str = Field(default="", description="文字摘要")
    evaluated_at: str = Field(default="", description="评估时间 ISO8601")


# ---------------------------------------------------------------------------
# Dialogue quality
# ---------------------------------------------------------------------------

class DialogueQualityResult(BaseModel):
    """Result of evaluating a dialogue session."""

    session_id: str = Field(default="", description="会话 ID")
    message_count: int = Field(default=0, description="消息数")
    overall_score: float = Field(default=0.0, ge=0.0, le=1.0, description="综合分数")
    grade: EvalGrade = Field(default=EvalGrade.POOR, description="综合评级")
    scores: list[EvalScore] = Field(default_factory=list, description="各维度得分")
    summary: str = Field(default="", description="文字摘要")
    evaluated_at: str = Field(default="", description="评估时间 ISO8601")


# ---------------------------------------------------------------------------
# Batch report
# ---------------------------------------------------------------------------

class EvalReport(BaseModel):
    """Batch evaluation report."""

    report_id: str = Field(default="", description="报告 ID")
    trajectory_results: list[TrajectoryEvalResult] = Field(
        default_factory=list, description="轨迹评估结果列表"
    )
    dialogue_results: list[DialogueQualityResult] = Field(
        default_factory=list, description="对话质量结果列表"
    )
    overall_score: float = Field(default=0.0, ge=0.0, le=1.0, description="批次综合分数")
    grade: EvalGrade = Field(default=EvalGrade.POOR, description="批次综合评级")
    summary: str = Field(default="", description="文字摘要")
    created_at: str = Field(default="", description="报告生成时间 ISO8601")
