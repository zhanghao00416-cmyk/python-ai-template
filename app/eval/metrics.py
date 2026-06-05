"""Dialogue quality metrics — algorithmic evaluation of chat quality.

Implements lightweight, deterministic metrics (no LLM calls):
- Response relevance via keyword overlap
- Response conciseness via length ratio
- Citation accuracy via source matching

Dependency: none (pure algorithms).
"""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger

logger = get_logger("eval.metrics")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize(text: str) -> set[str]:
    """Normalize text to a set of lower-cased tokens.

    - Latin script: word-level tokens (alphanumeric sequences)
    - CJK: individual character-level tokens
    """
    import re

    lowered = text.lower()
    # Word-level tokens for Latin scripts
    words = re.findall(r"[a-z0-9]+", lowered)
    # Character-level tokens for CJK Unified Ideographs
    cjk = re.findall(r"[\u4e00-\u9fff]", lowered)
    return set(words) | set(cjk)


def _clamp(value: float) -> float:
    """Clamp value to [0.0, 1.0]."""
    return max(0.0, min(1.0, value))


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def response_relevance(query: str, response: str) -> float:
    """Measure response relevance by token overlap with query.

    Returns 0.0-1.0 where 1.0 means all query tokens appear in response.
    """
    if not response:
        return 0.0

    query_tokens = _normalize(query)
    response_tokens = _normalize(response)

    if not query_tokens:
        return 1.0  # Empty query => nothing to match, avoid division by zero

    overlap = query_tokens & response_tokens
    score = len(overlap) / len(query_tokens)
    return _clamp(score)


def response_conciseness(response: str, *, max_length: int = 500) -> float:
    """Measure conciseness by inverse length penalty.

    - score = 1.0 if length <= max_length
    - score linearly decays to 0.0 at 3 * max_length
    """
    if not response:
        return 1.0  # Empty response is trivially concise

    length = len(response)
    if length <= max_length:
        return 1.0

    penalty_start = max_length
    penalty_end = 3 * max_length
    if length >= penalty_end:
        return 0.0

    score = 1.0 - (length - penalty_start) / (penalty_end - penalty_start)
    return _clamp(score)


def citation_accuracy(
    citations: list[dict[str, Any]],
    sources: list[dict[str, Any]] | None = None,
) -> float:
    """Measure citation accuracy by checking if cited filenames exist in sources.

    If *sources* is None, returns 1.0 (cannot verify).
    """
    if not citations:
        return 1.0  # No citations => nothing to verify

    if sources is None:
        return 1.0  # No ground truth => assume correct

    source_names = {s.get("filename", "") for s in sources if s.get("filename")}
    if not source_names:
        return 0.0

    matched = 0
    for c in citations:
        fname = c.get("filename", "")
        if fname in source_names:
            matched += 1

    score = matched / len(citations)
    return _clamp(score)


def dialogue_turn_balance(
    messages: list[dict[str, Any]],
) -> float:
    """Measure user/assistant turn balance (closer to 1:1 is better).

    Returns 1.0 for perfect alternation; lower for lopsided counts.
    """
    if not messages:
        return 0.0

    user_count = sum(1 for m in messages if m.get("role") == "user")
    assistant_count = sum(1 for m in messages if m.get("role") == "assistant")
    total = user_count + assistant_count

    if total == 0:
        return 0.0

    # Ideal ratio is 0.5 (equal counts); score = 1.0 - |ratio - 0.5| * 2
    ratio = user_count / total
    score = 1.0 - abs(ratio - 0.5) * 2
    return _clamp(score)
