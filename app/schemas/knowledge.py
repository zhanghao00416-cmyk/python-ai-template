"""Knowledge base Pydantic schemas."""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class ChunkingStrategy(str, Enum):
    """Supported document chunking strategies."""

    FIXED_OVERLAP = "fixed_overlap"
    DELIMITER_MAX = "delimiter_max"
    SEMANTIC = "semantic"
    PARAGRAPH = "paragraph"


class ChunkingParams(BaseModel):
    """Common chunking parameters shared by all strategies."""

    chunk_size: int = Field(default=500, ge=50, le=4000)
    chunk_overlap: int = Field(default=50, ge=0, le=1000)
    delimiter: str | None = Field(default=None)

    @field_validator("chunk_overlap")
    @classmethod
    def _overlap_lt_size(cls, v: int, info: Any) -> int:  # noqa: ANN401
        data = info.data
        size = data.get("chunk_size")
        if size is not None and v >= size:
            raise ValueError("chunk_overlap must be less than chunk_size")
        return v


class ParentChunkParams(BaseModel):
    """Parameters for parent chunks when parent-child mode is enabled."""

    chunk_size: int = Field(default=1000, ge=100, le=8000)
    chunk_overlap: int = Field(default=100, ge=0, le=2000)

    @field_validator("chunk_overlap")
    @classmethod
    def _overlap_lt_size(cls, v: int, info: Any) -> int:  # noqa: ANN401
        data = info.data
        size = data.get("chunk_size")
        if size is not None and v >= size:
            raise ValueError("chunk_overlap must be less than chunk_size")
        return v


class CollectionCreateRequest(BaseModel):
    """Request body for creating a knowledge collection."""

    name: str = Field(..., min_length=1, max_length=128)
    description: str = ""
    vector_dim: int = Field(default=1024, ge=2, le=4096)
    distance: str = "Cosine"
    sparse_vector: bool = True
    default_chunk_size: int = Field(default=500, ge=50, le=4000)
    default_chunk_overlap: int = Field(default=50, ge=0, le=1000)


class CollectionCreateResponse(BaseModel):
    """Response after creating a knowledge collection."""

    name: str
    status: str = "created"


class CollectionListItem(BaseModel):
    """Single collection entry in list response."""

    name: str
    vector_dim: int
    distance: str
    vectors_count: int = 0
    description: str = ""


class CollectionListResponse(BaseModel):
    """Response listing knowledge collections."""

    collections: list[CollectionListItem] = Field(default_factory=list)


class CollectionDeleteResponse(BaseModel):
    """Response after deleting a knowledge collection."""

    name: str
    deleted: bool


class DocumentUploadRequest(BaseModel):
    """Upload parameters for a knowledge document.

    This model mirrors the multipart form fields accepted by the upload endpoint.
    The actual file bytes are handled separately by FastAPI's UploadFile.
    """

    doc_type: str = Field(default="article", min_length=1, max_length=64)
    source: str = Field(default="", max_length=256)
    tag: str = Field(default="", max_length=256)
    strategy: ChunkingStrategy = ChunkingStrategy.FIXED_OVERLAP
    chunking_params: ChunkingParams = Field(default_factory=ChunkingParams)
    enable_parent_child: bool = False
    parent_chunk_params: ParentChunkParams = Field(default_factory=ParentChunkParams)


class DocumentUploadResponse(BaseModel):
    """Response after accepting a document upload."""

    task_id: str
    status: str = "pending"


class DocumentListItem(BaseModel):
    """Single document entry in list response."""

    doc_id: str
    doc_type: str
    source: str
    tag: str
    chunk_count: int
    source_file: str = ""
    created_at: str | None = None


class DocumentListResponse(BaseModel):
    """Response listing documents in a collection."""

    collection: str
    documents: list[DocumentListItem] = Field(default_factory=list)
    total: int = 0


class DocumentDeleteRequest(BaseModel):
    """Parameters for deleting documents from a collection."""

    doc_id: str | None = None
    source: str | None = None
    tag: str | None = None
    doc_type: str | None = None
    confirm_token: str | None = None


class DocumentDeletePreview(BaseModel):
    """Two-step confirmation preview for document deletion."""

    collection: str
    matched_count: int
    filters: dict[str, Any] = Field(default_factory=dict)
    confirm_token: str


class DocumentDeleteResponse(BaseModel):
    """Response after executing document deletion."""

    collection: str
    deleted_count: int
    confirm_token: str


# ------------------------------------------------------------------
# RAG Query
# ------------------------------------------------------------------

class RAGQueryRequest(BaseModel):
    """Request body for RAG query."""

    user_id: str = Field(..., min_length=1, max_length=128)
    session_id: str | None = Field(default=None, max_length=128)
    query: str = Field(..., min_length=1, max_length=8192)
    collection_names: list[str] | None = Field(default=None)
    doc_type: str | None = Field(default=None, max_length=64)
    source: str | None = Field(default=None, max_length=256)
    tag: str | None = Field(default=None, max_length=256)
    uploader: str | None = Field(default=None, max_length=128)
    retrieval_strategy: str = Field(default="hybrid")
    top_k: int = Field(default=5, ge=1, le=50)
    score_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    enable_rerank: bool = False
    stream: bool = True
    model_override: str | None = Field(default=None, max_length=64)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=4096, ge=1, le=16384)


class RAGCitation(BaseModel):
    """Single citation source."""

    filename: str
    chunk_text: str
    score: float


class RAGRetrievalResult(BaseModel):
    """Single retrieval result with optional parent context."""

    chunk_text: str
    score: float
    chunk_index: int = 0
    parent_chunk_text: str | None = None
    parent_chunk_index: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RAGUsage(BaseModel):
    """Token usage for RAG generation."""

    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""


class RAGQueryResponse(BaseModel):
    """Response for synchronous RAG query."""

    content: str
    citations: list[RAGCitation] = Field(default_factory=list)
    retrieval_results: list[RAGRetrievalResult] = Field(default_factory=list)
    usage: RAGUsage = Field(default_factory=RAGUsage)
