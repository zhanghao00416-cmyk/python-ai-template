"""Lightweight embedding service with external API and deterministic fallback."""
from __future__ import annotations

import asyncio
import hashlib
import math
import re
from typing import Any

import httpx
import structlog

from app.core.config import get_settings
from app.core.errors import AppError, ErrorCode

logger = structlog.get_logger(__name__)


class EmbeddingService:
    """Generate dense and sparse vectors for text chunks.

    Dense vectors are produced by an OpenAI-compatible embedding endpoint if
    configured; otherwise a deterministic hash-based fallback is used so tests
    and offline environments remain stable.

    Sparse vectors are computed with a simple term-frequency scheme compatible
    with Qdrant's sparse vector support.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._base_url = settings.embedding.get("base_url", "")
        self._model = settings.embedding.get("model", "bge-m3")
        self._api_key = settings.text_model.qwen_api_key
        self._timeout = settings.embedding.get("timeout", 60)
        self._dim = settings.embedding.get("dim", 1024)
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=float(self._timeout))
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Return a dense vector for each text.

        Falls back to deterministic hash vectors when no external endpoint is
        configured or when the call fails.
        """
        if not texts:
            return []

        if self._base_url:
            try:
                return await self._call_api(texts)
            except Exception as exc:
                logger.warning(
                    "embedding_api_failed",
                    error=str(exc),
                    fallback="hash",
                )

        return [_hash_vector(t, self._dim) for t in texts]

    async def _call_api(self, texts: list[str]) -> list[list[float]]:
        client = await self._get_client()
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        payload = {
            "model": self._model,
            "input": texts,
        }
        response = await client.post(
            f"{self._base_url.rstrip('/')}/embeddings",
            headers=headers,
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
        embeddings = sorted(data["data"], key=lambda x: x["index"])
        return [item["embedding"] for item in embeddings]

    def compute_sparse_vectors(self, texts: list[str]) -> list[dict[int, float]]:
        """Compute a simple TF-based sparse vector for each text.

        The resulting dictionaries use integer token ids as keys and
        log-scaled term frequencies as values. They are suitable for
        Qdrant's sparse vector fields.
        """
        if not texts:
            return []

        # Build a shared vocabulary for the batch so dimensions align.
        vocab: dict[str, int] = {}
        tokenized: list[list[str]] = []
        for text in texts:
            tokens = _tokenize(text)
            tokenized.append(tokens)
            for token in tokens:
                if token not in vocab:
                    vocab[token] = len(vocab)

        results: list[dict[int, float]] = []
        for tokens in tokenized:
            tf: dict[int, float] = {}
            for token in tokens:
                tid = vocab[token]
                tf[tid] = tf.get(tid, 0.0) + 1.0
            # Apply log scaling.
            for tid in tf:
                tf[tid] = 1.0 + math.log(tf[tid])
            results.append(tf)
        return results


def _tokenize(text: str) -> list[str]:
    """Simple alphanumeric tokenizer for sparse vector generation."""
    lowered = text.lower()
    tokens = re.findall(r"[a-z0-9\u4e00-\u9fff]+", lowered)
    return [t for t in tokens if len(t) > 1]


def _hash_vector(text: str, dim: int) -> list[float]:
    """Deterministic dense vector from text hash.

    Produces unit-normalized vectors of the requested dimension. Not
    semantically meaningful, but stable across runs and environments.
    """
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    # Use pairs of bytes to seed each dimension.
    vec = []
    for i in range(dim):
        byte_a = digest[(i * 2) % len(digest)]
        byte_b = digest[(i * 2 + 1) % len(digest)]
        value = ((byte_a << 8) + byte_b) / 65535.0
        vec.append(value)
    # Normalize to unit length.
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0:
        return vec
    return [v / norm for v in vec]
