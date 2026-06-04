from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from app.schemas.llm import LLMRequest, LLMResponse, LLMChunk


class LLMProvider(ABC):
    @abstractmethod
    async def generate(self, request: LLMRequest) -> LLMResponse:
        pass

    @abstractmethod
    async def generate_stream(self, request: LLMRequest) -> AsyncIterator[LLMChunk]:
        pass