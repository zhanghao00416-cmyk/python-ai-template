from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PayloadIndexConfig(BaseModel):
    field: str
    type: str = "keyword"


class CollectionConfig(BaseModel):
    name: str
    description: str = ""
    vector_dim: int = 1024
    distance: str = "Cosine"
    sparse_vector: bool = True
    payload_indexes: list[PayloadIndexConfig] = Field(default_factory=list)
    default_chunk_size: int = 500
    default_chunk_overlap: int = 50


class PointPayload(BaseModel):
    doc_id: str
    collection: str
    doc_type: str = ""
    source: str = ""
    tag: str = ""
    uploader: str = ""
    heading: str = ""
    heading_level: int = 0
    source_file: str = ""
    chunk_index: int = 0
    text: str = ""
    is_parent: bool = False
    parent_id: str | None = None


class PointInsert(BaseModel):
    id: str
    vector: list[float]
    sparse_vector: dict[int, float] | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class SearchResult(BaseModel):
    id: str
    score: float
    payload: dict[str, Any] = Field(default_factory=dict)


class RetrievalConfig(BaseModel):
    default_top_k: int = 3
    default_score_threshold: float = 0.5
    enable_hybrid: bool = True
    hybrid_alpha: float = 0.7
    enable_rerank: bool = False