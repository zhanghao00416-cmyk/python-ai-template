"""Intent classification domain service.

Three-layer funnel:
  L1: Keyword matching (fastest, zero LLM cost)
  L2: Similarity matching (embedding-based, low cost)
  L3: LLM classification (most accurate, highest cost)

Supports multi-intent detection and query reconstruction.
"""
from __future__ import annotations

import asyncio
import json
import math
import time
from typing import Any

import structlog

from app.core.config import get_settings
from app.core.errors import AppError, ErrorCode, IntentError, make_error
from app.schemas.intent import IntentResultData, RoutingInfo, SubIntent
from app.schemas.llm import LLMRequest, Message
from app.services.embedding import EmbeddingService
from app.services.llm.gateway import LLMGateway
from app.services.prompt_manager import PromptManager

logger = structlog.get_logger("domain.intent.service")


class _KeywordResult:
    def __init__(self, intent: str, confidence: float, query: str) -> None:
        self.intent = intent
        self.confidence = confidence
        self.query = query


class _SimilarityResult:
    def __init__(self, intent: str, confidence: float, query: str) -> None:
        self.intent = intent
        self.confidence = confidence
        self.query = query


class _LLMResult:
    def __init__(
        self,
        intent: str,
        confidence: float,
        query: str,
        sub_intents: list[SubIntent],
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        self.intent = intent
        self.confidence = confidence
        self.query = query
        self.sub_intents = sub_intents
        self.model = model
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class KeywordMatcher:
    """L1: Keyword-based intent matching."""

    def __init__(self, rules: list[dict[str, Any]], threshold: float = 0.9) -> None:
        self._rules = rules
        self._threshold = threshold

    def match(self, query: str) -> _KeywordResult | None:
        text = query.lower()
        best_intent: str | None = None
        best_score = 0.0

        for rule in self._rules:
            intent = rule.get("intent", "")
            keywords = rule.get("keywords", [])
            if not intent or not keywords:
                continue

            matched = sum(1 for kw in keywords if kw.lower() in text)
            if matched:
                score = min(matched / len(keywords), 1.0)
                if score > best_score:
                    best_score = score
                    best_intent = intent

        if best_intent and best_score >= self._threshold:
            return _KeywordResult(intent=best_intent, confidence=best_score, query=query)
        return None


class SimilarityMatcher:
    """L2: Embedding-based similarity matching."""

    def __init__(
        self,
        embedding_service: EmbeddingService,
        representatives: dict[str, str],
        threshold: float = 0.85,
        top_k: int = 3,
    ) -> None:
        self._embedding = embedding_service
        self._representatives = representatives
        self._threshold = threshold
        self._top_k = top_k

    async def match(self, query: str) -> _SimilarityResult | None:
        if not self._representatives:
            return None

        texts = [query] + list(self._representatives.values())
        embeddings = await self._embedding.embed_batch(texts)
        if len(embeddings) < 2:
            return None

        query_vec = embeddings[0]
        rep_vecs = embeddings[1:]
        rep_names = list(self._representatives.keys())

        scored: list[tuple[float, str]] = []
        for name, vec in zip(rep_names, rep_vecs):
            score = _cosine_similarity(query_vec, vec)
            scored.append((score, name))

        scored.sort(reverse=True)
        if scored and scored[0][0] >= self._threshold:
            return _SimilarityResult(
                intent=scored[0][1],
                confidence=scored[0][0],
                query=query,
            )
        return None


class LLMClassifier:
    """L3: LLM-based intent classification with multi-intent support."""

    def __init__(
        self,
        llm_gateway: LLMGateway,
        prompt_manager: PromptManager,
        max_intents: int = 3,
    ) -> None:
        self._llm = llm_gateway
        self._prompts = prompt_manager
        self._max_intents = max_intents

    async def classify(
        self,
        query: str,
        candidates: list[str] | None = None,
    ) -> _LLMResult:
        try:
            prompt = self._prompts.render(
                "intent/classify",
                {
                    "query": query,
                    "candidates": ", ".join(candidates) if candidates else "",
                },
            )
        except KeyError as exc:
            raise IntentError(
                code=ErrorCode.INTENT_CLASSIFY_FAILED,
                message=f"Prompt template not found: {exc}",
            ) from exc

        messages = [
            Message(role="system", content=prompt),
            Message(role="user", content=query),
        ]

        llm_request = LLMRequest(
            messages=messages,
            task_type="intent",
            temperature=0.1,
            max_tokens=512,
            stream=False,
        )

        try:
            response = await self._llm.generate(llm_request)
        except AppError:
            raise
        except Exception as exc:
            logger.error("intent_llm_call_failed", error=str(exc))
            raise IntentError(
                code=ErrorCode.INTENT_CLASSIFY_FAILED,
                message="LLM classification call failed",
            ) from exc

        raw = response.content.strip()
        parsed = _parse_llm_json(raw)
        if parsed is None:
            raise IntentError(
                code=ErrorCode.INTENT_CLASSIFY_FAILED,
                message="LLM returned unparseable JSON",
            )

        primary = parsed.get("primary_intent", "")
        confidence = float(parsed.get("confidence", 0.0))
        sub_intents_raw = parsed.get("sub_intents", [])
        sub_intents: list[SubIntent] = []

        for idx, si in enumerate(sub_intents_raw):
            if idx >= self._max_intents:
                break
            si_intent = si.get("intent", "")
            if not si_intent:
                continue
            sub_intents.append(
                SubIntent(
                    intent=si_intent,
                    confidence=float(si.get("confidence", 0.0)),
                    query=si.get("query", si.get("original_query", "")),
                    original_query=si.get("original_query", ""),
                )
            )

        # Validate against candidates
        allowed = candidates or ["qa", "task", "chat", "retrieve_only"]
        if primary not in allowed:
            raise IntentError(
                code=ErrorCode.INTENT_UNKNOWN,
                message=f"LLM returned unknown intent: {primary}",
            )

        return _LLMResult(
            intent=primary,
            confidence=confidence,
            query=parsed.get("query", query),
            sub_intents=sub_intents,
            model=response.model,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
        )


class IntentDomainService:
    """Domain service for intent classification.

    Orchestrates L1 -> L2 -> L3 with early-exit and fallback handling.
    """

    def __init__(
        self,
        llm_gateway: LLMGateway,
        prompt_manager: PromptManager,
        embedding_service: EmbeddingService | None = None,
    ) -> None:
        self._llm = llm_gateway
        self._prompts = prompt_manager
        self._embedding = embedding_service or EmbeddingService()

        settings = get_settings()
        self._intent_cfg: dict[str, Any] = getattr(settings, "intent", {})
        self._fallback = self._intent_cfg.get("fallback_intent", "chat")
        self._max_input_length = self._intent_cfg.get("max_input_length", 1000)
        self._timeout = float(self._intent_cfg.get("timeout", 5.0))

    async def classify(
        self,
        query: str,
        candidates: list[str] | None = None,
        options: dict[str, bool] | None = None,
    ) -> IntentResultData:
        opts = options or {}
        keyword_enabled = opts.get("keyword_enabled", True)
        similarity_enabled = opts.get("similarity_enabled", True)
        multi_intent_enabled = opts.get("multi_intent_enabled", True)

        # Boundary: input too short
        if len(query.strip()) < 3:
            return self._fallback_result(query, "fallback", "输入过短")

        # Boundary: input too long
        if len(query) > self._max_input_length:
            query = query[: self._max_input_length]

        layers_cfg = self._intent_cfg.get("layers", {})
        keyword_cfg = layers_cfg.get("keyword", {})
        similarity_cfg = layers_cfg.get("similarity", {})
        llm_cfg = layers_cfg.get("llm", {})
        multi_intent_cfg = self._intent_cfg.get("multi_intent", {})

        # L1: Keyword
        if keyword_enabled and keyword_cfg.get("enabled", True):
            matcher = KeywordMatcher(
                rules=keyword_cfg.get("rules", []),
                threshold=keyword_cfg.get("confidence_threshold", 0.9),
            )
            result = matcher.match(query)
            if result:
                return self._build_result(
                    result.intent,
                    result.confidence,
                    result.query,
                    "keyword",
                    [],
                )

        # L2: Similarity
        if similarity_enabled and similarity_cfg.get("enabled", True):
            matcher = SimilarityMatcher(
                embedding_service=self._embedding,
                representatives=similarity_cfg.get("representatives", {}),
                threshold=similarity_cfg.get("score_threshold", 0.85),
                top_k=similarity_cfg.get("top_k", 3),
            )
            result = await matcher.match(query)
            if result:
                return self._build_result(
                    result.intent,
                    result.confidence,
                    result.query,
                    "similarity",
                    [],
                )

        # L3: LLM
        if llm_cfg.get("enabled", True):
            try:
                classifier = LLMClassifier(
                    llm_gateway=self._llm,
                    prompt_manager=self._prompts,
                    max_intents=multi_intent_cfg.get("max_intents", 3) if multi_intent_enabled else 0,
                )
                llm_result = await asyncio.wait_for(
                    classifier.classify(query, candidates=candidates),
                    timeout=self._timeout,
                )
                sub_intents = llm_result.sub_intents if multi_intent_enabled else []
                return self._build_result(
                    llm_result.intent,
                    llm_result.confidence,
                    llm_result.query,
                    "llm",
                    sub_intents,
                )
            except asyncio.TimeoutError as exc:
                logger.warning("intent_classification_timeout", query=query)
                return self._fallback_result(query, "fallback", "分类超时")
            except AppError:
                raise
            except Exception as exc:
                logger.error("intent_classification_failed", error=str(exc))
                return self._fallback_result(query, "fallback", str(exc))

        # All layers exhausted
        return self._fallback_result(query, "fallback", "无法确定意图")

    def _build_result(
        self,
        intent: str,
        confidence: float,
        query: str,
        layer_used: str,
        sub_intents: list[SubIntent],
    ) -> IntentResultData:
        routing_map = {
            "qa": RoutingInfo(workflow_id="rag_qa", model="qwen-plus"),
            "task": RoutingInfo(workflow_id="task_workflow", model="qwen-plus"),
            "chat": RoutingInfo(workflow_id="chat", model="qwen-plus"),
            "retrieve_only": RoutingInfo(workflow_id="rag_retrieve", model="qwen-plus"),
        }
        return IntentResultData(
            intent=intent,
            confidence=confidence,
            query=query,
            layer_used=layer_used,
            routing=routing_map.get(intent, RoutingInfo()),
            sub_intents=sub_intents,
        )

    def _fallback_result(
        self,
        query: str,
        layer_used: str,
        reason: str,
    ) -> IntentResultData:
        logger.info("intent_fallback", reason=reason, query=query)
        return self._build_result(
            intent=self._fallback,
            confidence=0.0,
            query=query,
            layer_used=layer_used,
            sub_intents=[],
        )


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _parse_llm_json(raw: str) -> dict[str, Any] | None:
    """Parse JSON from LLM output, handling markdown fences."""
    text = raw.strip()
    # Strip markdown fences
    if text.startswith("```"):
        lines = text.splitlines()
        # Remove first fence line
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        # Remove last fence line
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to find JSON object within text
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass

    return None
