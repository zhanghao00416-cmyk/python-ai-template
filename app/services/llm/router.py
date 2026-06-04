from __future__ import annotations

from typing import Any

import structlog

from app.core.config import get_settings, _load_yaml, _CONFIG_DIR
from app.services.llm.providers.base import LLMProvider
from app.services.llm.providers.qwen_cloud import QwenCloudProvider
from app.services.llm.providers.vllm import VLLMProvider

logger = structlog.get_logger(__name__)

TASK_TYPES = {"intent", "rag_rewrite", "rag_merge", "final", "chat", "multimodal", "embedding"}

_ROUTING_CACHE: dict[str, Any] | None = None


def _load_routing() -> dict[str, Any]:
    global _ROUTING_CACHE
    if _ROUTING_CACHE is not None:
        return _ROUTING_CACHE
    models_cfg = _load_yaml(_CONFIG_DIR / "models.yaml")
    routing = models_cfg.get("routing", {})
    _ROUTING_CACHE = routing
    return _ROUTING_CACHE


def reset_routing_cache() -> None:
    global _ROUTING_CACHE
    _ROUTING_CACHE = None


class LLMRouter:
    def __init__(self) -> None:
        self._routing: dict[str, Any] | None = None

    @property
    def routing(self) -> dict[str, Any]:
        if self._routing is None:
            self._routing = _load_routing()
        return self._routing

    def select_provider(
        self,
        task_type: str,
        model: str | None = None,
    ) -> LLMProvider:
        settings = get_settings()

        if model is not None:
            return self._create_provider_by_name(model, settings)

        task_routing = self.routing.get(task_type, {})
        if task_type == "embedding":
            provider_name = task_routing.get("provider", settings.text_model.text_model_provider)
            if provider_name == "vllm":
                return VLLMProvider()
            return QwenCloudProvider()

        provider_name = task_routing.get("provider", settings.text_model.text_model_provider)

        if provider_name == "qwen_cloud":
            return QwenCloudProvider()
        elif provider_name == "vllm":
            return VLLMProvider()
        else:
            return QwenCloudProvider()

    def select_fallback_provider(
        self,
        task_type: str,
    ) -> LLMProvider | None:
        settings = get_settings()
        task_routing = self.routing.get(task_type, {})
        primary = task_routing.get("provider", settings.text_model.text_model_provider)

        if primary == "qwen_cloud":
            if task_type == "multimodal":
                return None
            return VLLMProvider()
        return QwenCloudProvider()

    def _create_provider_by_name(self, model: str, settings: Any) -> LLMProvider:
        if model.startswith("openai/"):
            model = model[len("openai/"):]

        vllm_base = settings.text_model.text_vllm_base_url
        if vllm_base and not model.startswith("qwen"):
            return VLLMProvider(model=model)

        return QwenCloudProvider(default_model=model)