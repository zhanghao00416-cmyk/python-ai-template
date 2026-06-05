"""Evaluation runner — batch execution of eval tasks.

Orchestrates trajectory and dialogue quality evaluations,
produces structured reports.

Dependency: app/eval/metrics, app/eval/trajectory_eval,
            app/schemas/eval, app/agent/trajectory.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from app.core.logging import get_logger

if TYPE_CHECKING:
    from app.agent.trajectory import TrajectoryEntry
from app.eval.metrics import (
    citation_accuracy,
    dialogue_turn_balance,
    response_conciseness,
    response_relevance,
)
from app.eval.trajectory_eval import (
    loop_detection,
    state_transition_validity,
    step_efficiency,
    tool_call_success_rate,
    trajectory_completeness,
)
from app.schemas.eval import (
    DialogueQualityResult,
    EvalDimension,
    EvalGrade,
    EvalReport,
    EvalScore,
    TrajectoryEvalResult,
)

logger = get_logger("eval.runner")


# ---------------------------------------------------------------------------
# Grade mapping
# ---------------------------------------------------------------------------

def _to_grade(score: float) -> EvalGrade:
    """Map 0.0-1.0 score to qualitative grade."""
    if score >= 0.9:
        return EvalGrade.EXCELLENT
    if score >= 0.7:
        return EvalGrade.GOOD
    if score >= 0.5:
        return EvalGrade.FAIR
    return EvalGrade.POOR


def _average(scores: list[float]) -> float:
    """Safely compute mean of scores."""
    if not scores:
        return 0.0
    return sum(scores) / len(scores)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

class EvalRunner:
    """Batch evaluation executor.

    Usage::

        runner = EvalRunner()
        report = runner.run_batch(
            trajectories=[t1, t2],
            dialogues=[d1],
        )
    """

    def __init__(self) -> None:
        pass

    # -- trajectory evaluation -----------------------------------------------

    def run_trajectory_eval(
        self,
        trajectory: list[TrajectoryEntry],
        *,
        agent_name: str = "",
        agent_type: str = "",
        max_steps: int = 10,
    ) -> TrajectoryEvalResult:
        """Evaluate a single Agent trajectory."""
        if not trajectory:
            logger.warning("eval.runner.empty_trajectory")
            return TrajectoryEvalResult(
                agent_name=agent_name,
                agent_type=agent_type,
                total_steps=0,
                overall_score=0.0,
                grade=EvalGrade.POOR,
                scores=[
                    EvalScore(
                        dimension=EvalDimension.TRAJECTORY_COMPLETENESS,
                        score=0.0,
                        grade=EvalGrade.POOR,
                        issues=["Empty trajectory"],
                    )
                ],
                summary="Empty trajectory — cannot evaluate.",
                evaluated_at=datetime.now(UTC).isoformat(),
            )

        scores: list[EvalScore] = []
        issues: list[str] = []

        # 1. State transition validity
        stv = state_transition_validity(trajectory)
        scores.append(EvalScore(
            dimension=EvalDimension.STATE_TRANSITION_VALIDITY,
            score=stv["score"],
            grade=_to_grade(stv["score"]),
            details={"invalid_count": stv["invalid_count"], "total": stv["total_transitions"]},
            issues=stv["violations"][:5],  # Cap issues
        ))
        issues.extend(stv["violations"])

        # 2. Tool call success rate
        tcsr = tool_call_success_rate(trajectory)
        scores.append(EvalScore(
            dimension=EvalDimension.TOOL_CALL_SUCCESS_RATE,
            score=tcsr["score"],
            grade=_to_grade(tcsr["score"]),
            details={"total": tcsr["total"], "success": tcsr["success"], "failed": tcsr["failed"]},
            issues=[f"{tcsr['failed']} tool call(s) failed"] if tcsr["failed"] > 0 else [],
        ))

        # 3. Loop detection
        ld = loop_detection(trajectory)
        scores.append(EvalScore(
            dimension=EvalDimension.LOOP_DETECTION,
            score=ld["score"],
            grade=_to_grade(ld["score"]),
            details={"loops_detected": ld["loops_detected"]},
            issues=ld["details"][:5],
        ))

        # 4. Step efficiency
        se = step_efficiency(trajectory, max_steps=max_steps)
        scores.append(EvalScore(
            dimension=EvalDimension.STEP_EFFICIENCY,
            score=se["score"],
            grade=_to_grade(se["score"]),
            details={"steps": se["steps"], "max_steps": se["max_steps"]},
            issues=[f"Exceeded max_steps ({se['steps']} > {max_steps})"] if not se["efficient"] else [],
        ))

        # 5. Trajectory completeness
        tc = trajectory_completeness(trajectory)
        scores.append(EvalScore(
            dimension=EvalDimension.TRAJECTORY_COMPLETENESS,
            score=tc["score"],
            grade=_to_grade(tc["score"]),
            details={
                "has_thinking": tc["has_thinking"],
                "has_acting": tc["has_acting"],
                "has_observing": tc["has_observing"],
                "has_done": tc["has_done"],
                "has_error": tc["has_error"],
            },
            issues=[f"Missing phase(s): {', '.join(tc['missing'])}"] if tc["missing"] else [],
        ))

        overall = _average([s.score for s in scores])
        summary = (
            f"Trajectory ({agent_name}, {len(trajectory)} steps): "
            f"overall={overall:.2f}, grade={_to_grade(overall).value}. "
            f"Issues: {len(issues)}."
        )

        logger.info(
            "eval.runner.trajectory_done",
            agent_name=agent_name,
            steps=len(trajectory),
            overall=overall,
        )

        return TrajectoryEvalResult(
            agent_name=agent_name,
            agent_type=agent_type,
            total_steps=len(trajectory),
            overall_score=round(overall, 4),
            grade=_to_grade(overall),
            scores=scores,
            summary=summary,
            evaluated_at=datetime.now(UTC).isoformat(),
        )

    # -- dialogue quality evaluation -----------------------------------------

    def run_dialogue_eval(
        self,
        messages: list[dict[str, Any]],
        *,
        session_id: str = "",
        query: str = "",
        response: str = "",
        citations: list[dict[str, Any]] | None = None,
        sources: list[dict[str, Any]] | None = None,
    ) -> DialogueQualityResult:
        """Evaluate a single dialogue turn or full session."""
        if not messages and not response:
            logger.warning("eval.runner.empty_dialogue")
            return DialogueQualityResult(
                session_id=session_id,
                message_count=0,
                overall_score=0.0,
                grade=EvalGrade.POOR,
                scores=[
                    EvalScore(
                        dimension=EvalDimension.RESPONSE_RELEVANCE,
                        score=0.0,
                        grade=EvalGrade.POOR,
                        issues=["No dialogue data"],
                    )
                ],
                summary="Empty dialogue — cannot evaluate.",
                evaluated_at=datetime.now(UTC).isoformat(),
            )

        scores: list[EvalScore] = []

        # 1. Response relevance
        rel_score = response_relevance(query, response)
        scores.append(EvalScore(
            dimension=EvalDimension.RESPONSE_RELEVANCE,
            score=rel_score,
            grade=_to_grade(rel_score),
            details={"query_tokens": len(query.split()), "response_tokens": len(response.split())},
            issues=["Low relevance"] if rel_score < 0.3 else [],
        ))

        # 2. Response conciseness
        conc_score = response_conciseness(response)
        scores.append(EvalScore(
            dimension=EvalDimension.RESPONSE_CONCISENESS,
            score=conc_score,
            grade=_to_grade(conc_score),
            details={"response_length": len(response)},
            issues=["Response too long"] if conc_score < 0.3 else [],
        ))

        # 3. Citation accuracy
        cit_score = citation_accuracy(citations or [], sources)
        scores.append(EvalScore(
            dimension=EvalDimension.CITATION_ACCURACY,
            score=cit_score,
            grade=_to_grade(cit_score),
            details={"citations": len(citations or []), "sources": len(sources or [])},
            issues=["Citations unmatched"] if cit_score < 1.0 else [],
        ))

        # 4. Turn balance (if full session provided)
        if messages:
            bal_score = dialogue_turn_balance(messages)
            scores.append(EvalScore(
                dimension=EvalDimension.RESPONSE_RELEVANCE,  # Re-use dimension for balance (simplification)
                score=bal_score,
                grade=_to_grade(bal_score),
                details={"user_turns": sum(1 for m in messages if m.get("role") == "user")},
                issues=["Turn imbalance"] if bal_score < 0.5 else [],
            ))

        overall = _average([s.score for s in scores])
        summary = (
            f"Dialogue ({session_id}): overall={overall:.2f}, grade={_to_grade(overall).value}. "
            f"Messages: {len(messages)}, Response length: {len(response)}."
        )

        logger.info(
            "eval.runner.dialogue_done",
            session_id=session_id,
            overall=overall,
        )

        return DialogueQualityResult(
            session_id=session_id,
            message_count=len(messages),
            overall_score=round(overall, 4),
            grade=_to_grade(overall),
            scores=scores,
            summary=summary,
            evaluated_at=datetime.now(UTC).isoformat(),
        )

    # -- batch evaluation ----------------------------------------------------

    def run_batch(
        self,
        *,
        trajectories: list[tuple[list[TrajectoryEntry], dict[str, Any]]] | None = None,
        dialogues: list[dict[str, Any]] | None = None,
    ) -> EvalReport:
        """Run batch evaluation over multiple trajectories and dialogues.

        Args:
            trajectories: list of (trajectory_entries, metadata) tuples.
                metadata keys: agent_name, agent_type, max_steps.
            dialogues: list of dialogue dicts.
                keys: session_id, messages, query, response, citations, sources.
        """
        trajectory_results: list[TrajectoryEvalResult] = []
        dialogue_results: list[DialogueQualityResult] = []
        all_scores: list[float] = []

        if trajectories:
            for traj, meta in trajectories:
                result = self.run_trajectory_eval(
                    traj,
                    agent_name=meta.get("agent_name", ""),
                    agent_type=meta.get("agent_type", ""),
                    max_steps=meta.get("max_steps", 10),
                )
                trajectory_results.append(result)
                all_scores.append(result.overall_score)

        if dialogues:
            for dlg in dialogues:
                result = self.run_dialogue_eval(
                    messages=dlg.get("messages", []),
                    session_id=dlg.get("session_id", ""),
                    query=dlg.get("query", ""),
                    response=dlg.get("response", ""),
                    citations=dlg.get("citations"),
                    sources=dlg.get("sources"),
                )
                dialogue_results.append(result)
                all_scores.append(result.overall_score)

        overall = _average(all_scores)
        total = len(trajectory_results) + len(dialogue_results)
        summary = (
            f"Batch report: {total} item(s) evaluated. "
            f"Trajectories: {len(trajectory_results)}, Dialogues: {len(dialogue_results)}. "
            f"Overall score: {overall:.2f}."
        )

        logger.info(
            "eval.runner.batch_done",
            total=total,
            overall=overall,
        )

        return EvalReport(
            report_id=str(uuid.uuid4()),
            trajectory_results=trajectory_results,
            dialogue_results=dialogue_results,
            overall_score=round(overall, 4),
            grade=_to_grade(overall),
            summary=summary,
            created_at=datetime.now(UTC).isoformat(),
        )
