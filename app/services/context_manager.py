from __future__ import annotations

import asyncio
import structlog
from uuid import UUID
from typing import Any

from app.core.errors import SystemError, ErrorCode
from app.schemas.session import (
    ContextWindowResult,
    MessageDetail,
    TruncationStrategy,
)

logger = structlog.get_logger("services.context_manager")

try:
    import tiktoken

    _TIKTOKEN_AVAILABLE = True
except ImportError:
    _TIKTOKEN_AVAILABLE = False


def count_tokens(text: str, model: str = "cl100k_base") -> int:
    """Count tokens using tiktoken if available, otherwise approximate.

    Default encoding 'cl100k_base' covers GPT-4/4o family;
    fallback uses ~4 chars per token approximation.
    """
    if not text:
        return 0
    if _TIKTOKEN_AVAILABLE:
        try:
            enc = tiktoken.get_encoding(model)
            return len(enc.encode(text))
        except Exception:
            pass
    return max(1, len(text) // 4)


class ContextManager:
    """Manages session context windows with token-budget truncation.

    Responsibilities:
    - Build context windows from session messages within token budget
    - Support 3 truncation strategies: recent_priority, summary, sliding_window
    - Cache context windows in Redis for fast retrieval
    - Gracefully degrade to DB-only mode when Redis is unavailable
    """

    def __init__(
        self,
        redis_client: Any = None,
        cache_ttl: int = 3600,
        default_max_tokens: int = 4096,
        default_strategy: str = "recent_priority",
    ) -> None:
        self._redis_client = redis_client
        self._cache_ttl = cache_ttl
        self._default_max_tokens = default_max_tokens
        self._default_strategy = default_strategy

    async def get_context_window(
        self,
        session_id: UUID,
        messages: list[MessageDetail],
        max_tokens: int | None = None,
        strategy: str | None = None,
        system_prompt: str | None = None,
    ) -> ContextWindowResult:
        """Build a context window within token budget.

        Args:
            session_id: Session identifier
            messages: List of messages (already fetched from DB, newest last)
            max_tokens: Maximum token budget (defaults to config value)
            strategy: Truncation strategy name
            system_prompt: Optional system prompt prepended to window

        Returns:
            ContextWindowResult with truncated messages and metadata
        """
        budget = max_tokens or self._default_max_tokens
        strat_name = strategy or self._default_strategy
        strat = TruncationStrategy(strat_name)

        system_tokens = count_tokens(system_prompt) if system_prompt else 0
        remaining = budget - system_tokens

        if remaining <= 0:
            return ContextWindowResult(
                session_id=session_id,
                system_prompt=system_prompt,
                messages=[],
                total_tokens=system_tokens,
                truncated=True,
                summary=None,
            )

        truncated_msgs, summary = self._apply_strategy(
            messages, remaining, strat
        )

        total = system_tokens + sum(
            count_tokens(m.content or "") for m in truncated_msgs
        )

        result = ContextWindowResult(
            session_id=session_id,
            system_prompt=system_prompt,
            messages=truncated_msgs,
            total_tokens=total,
            truncated=len(truncated_msgs) < len(messages) or total > budget,
            summary=summary,
        )

        await self._cache_context(session_id, result)
        return result

    def _apply_strategy(
        self,
        messages: list[MessageDetail],
        token_budget: int,
        strategy: TruncationStrategy,
    ) -> tuple[list[MessageDetail], str | None]:
        """Apply truncation strategy to fit messages within token budget.

        Messages are expected in chronological order (oldest first).
        """
        if strategy == TruncationStrategy.RECENT_PRIORITY:
            return self._strategy_recent_priority(messages, token_budget)
        elif strategy == TruncationStrategy.SLIDING_WINDOW:
            return self._strategy_sliding_window(messages, token_budget)
        elif strategy == TruncationStrategy.SUMMARY:
            return self._strategy_summary(messages, token_budget)
        else:
            return self._strategy_recent_priority(messages, token_budget)

    def _strategy_recent_priority(
        self,
        messages: list[MessageDetail],
        token_budget: int,
    ) -> tuple[list[MessageDetail], None]:
        """Keep most recent messages, drop oldest to fit budget."""
        selected: list[MessageDetail] = []
        used = 0
        for msg in reversed(messages):
            msg_tokens = count_tokens(msg.content or "")
            if used + msg_tokens > token_budget:
                break
            selected.insert(0, msg)
            used += msg_tokens
        return selected, None

    def _strategy_sliding_window(
        self,
        messages: list[MessageDetail],
        token_budget: int,
    ) -> tuple[list[MessageDetail], None]:
        """Fixed-size window of last N messages that fit in budget."""
        if not messages:
            return [], None
        selected: list[MessageDetail] = []
        used = 0
        for msg in reversed(messages):
            msg_tokens = count_tokens(msg.content or "")
            if used + msg_tokens > token_budget:
                break
            selected.insert(0, msg)
            used += msg_tokens
        return selected, None

    def _strategy_summary(
        self,
        messages: list[MessageDetail],
        token_budget: int,
    ) -> tuple[list[MessageDetail], str | None]:
        """Summary strategy: reserve 30% for summary of dropped msgs, rest for recent msgs."""
        summary_budget = max(1, int(token_budget * 0.3))
        recent_budget = token_budget - summary_budget

        recent: list[MessageDetail] = []
        used = 0
        for msg in reversed(messages):
            msg_tokens = count_tokens(msg.content or "")
            if used + msg_tokens > recent_budget:
                break
            recent.insert(0, msg)
            used += msg_tokens

        cutoff_idx = messages.index(recent[0]) if recent else len(messages)
        dropped = messages[:cutoff_idx]
        summary_text = self._generate_summary_text(dropped)
        summary_tokens = count_tokens(summary_text)
        if summary_tokens > summary_budget:
            char_limit = summary_budget * 4
            summary_text = summary_text[:char_limit] + "..."

        return recent, summary_text

    @staticmethod
    def _generate_summary_text(dropped: list[MessageDetail]) -> str:
        """Generate a simple summary from dropped messages (no LLM call in F09)."""
        if not dropped:
            return ""
        parts: list[str] = []
        for msg in dropped:
            role = msg.role
            content_preview = (msg.content or "")[:200]
            parts.append(f"[{role}]: {content_preview}")
        combined = "\n".join(parts)
        prefix = f"Summary of {len(dropped)} earlier message(s):\n"
        return prefix + combined

    async def _cache_context(
        self, session_id: UUID, result: ContextWindowResult
    ) -> None:
        """Cache context window in Redis; degrade silently if unavailable."""
        if self._redis_client is None:
            return
        try:
            key = f"session_ctx:{session_id}"
            mapping: dict[str, str] = {
                "total_tokens": str(result.total_tokens),
                "truncated": str(result.truncated),
                "message_count": str(len(result.messages)),
            }
            if result.summary:
                mapping["summary"] = result.summary
            if result.system_prompt:
                mapping["system_prompt"] = result.system_prompt
            await self._redis_client.hset(key, mapping=mapping)
            await self._redis_client.client.expire(key, self._cache_ttl)
            logger.debug("context.cached", session_id=str(session_id))
        except Exception as exc:
            logger.warning("context.cache_failed", session_id=str(session_id), error=str(exc))

    async def invalidate_cache(self, session_id: UUID) -> None:
        """Invalidate context cache when new message is added."""
        if self._redis_client is None:
            return
        try:
            key = f"session_ctx:{session_id}"
            await self._redis_client.delete(key)
            logger.debug("context.cache_invalidated", session_id=str(session_id))
        except Exception as exc:
            logger.warning("context.cache_invalidate_failed", session_id=str(session_id), error=str(exc))

    async def get_cached_context(self, session_id: UUID) -> dict[str, str] | None:
        """Get cached context metadata from Redis; return None on miss or error."""
        if self._redis_client is None:
            return None
        try:
            key = f"session_ctx:{session_id}"
            data = await self._redis_client.hgetall(key)
            if not data:
                return None
            return data
        except Exception as exc:
            logger.warning("context.cache_read_failed", session_id=str(session_id), error=str(exc))
            return None