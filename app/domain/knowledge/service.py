"""Knowledge base domain service: collections, document management, and RAG query."""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import structlog

from app.core.config import get_settings
from app.core.errors import AppError, ErrorCode, KnowledgeError, RAGError, make_error
from app.domain.knowledge.repo import KnowledgeRepo
from app.domain.task.service import TaskService
from app.schemas.knowledge import (
    ChunkingParams,
    ChunkingStrategy,
    CollectionCreateRequest,
    CollectionCreateResponse,
    CollectionDeleteResponse,
    CollectionListItem,
    CollectionListResponse,
    DocumentDeletePreview,
    DocumentDeleteRequest,
    DocumentDeleteResponse,
    DocumentListItem,
    DocumentListResponse,
    DocumentUploadRequest,
    DocumentUploadResponse,
    ParentChunkParams,
    RAGCitation,
    RAGQueryRequest,
    RAGQueryResponse,
    RAGRetrievalResult,
    RAGUsage,
)
from app.schemas.llm import LLMRequest, Message
from app.schemas.vector_store import CollectionConfig, PayloadIndexConfig, PointPayload, SearchResult
from app.services.chunking import ChunkingService
from app.services.embedding import EmbeddingService
from app.services.llm.gateway import LLMGateway
from app.services.prompt_manager import PromptManager
from app.services.sse_stream import SSEStreamService

logger = structlog.get_logger("domain.knowledge.service")


class KnowledgeService:
    """Domain service for knowledge base collections, documents, and RAG query.

    Responsibilities:
    - Create / list / delete collections
    - Accept document uploads and dispatch async ingestion tasks
    - List documents with metadata filters
    - Delete documents with two-step confirmation
    - RAG query with 4 retrieval strategies + rerank + parent-child context
    """

    def __init__(
        self,
        repo: KnowledgeRepo,
        task_service: TaskService,
        chunking_service: ChunkingService | None = None,
        embedding_service: EmbeddingService | None = None,
        llm_gateway: LLMGateway | None = None,
        prompt_manager: PromptManager | None = None,
    ) -> None:
        self._repo = repo
        self._task_service = task_service
        self._chunking = chunking_service or ChunkingService()
        self._embedding = embedding_service or EmbeddingService()
        self._llm = llm_gateway
        self._prompts = prompt_manager

    # ------------------------------------------------------------------
    # Collections
    # ------------------------------------------------------------------

    async def create_collection(
        self, request: CollectionCreateRequest
    ) -> CollectionCreateResponse:
        config = CollectionConfig(
            name=request.name,
            description=request.description,
            vector_dim=request.vector_dim,
            distance=request.distance,
            sparse_vector=True,
            payload_indexes=_default_payload_indexes(),
            default_chunk_size=request.default_chunk_size,
            default_chunk_overlap=request.default_chunk_overlap,
        )
        await self._repo.create_collection(config)
        return CollectionCreateResponse(name=request.name, status="created")

    async def list_collections(self) -> CollectionListResponse:
        infos = await self._repo.list_collections()
        items = [
            CollectionListItem(
                name=info["name"],
                vector_dim=info.get("vector_dim", 1024),
                distance=info.get("distance", "Cosine"),
                vectors_count=info.get("points_count", 0),
                description=info.get("description", ""),
            )
            for info in infos
        ]
        return CollectionListResponse(collections=items)

    async def delete_collection(self, name: str) -> CollectionDeleteResponse:
        await self._repo.delete_collection(name)
        return CollectionDeleteResponse(name=name, deleted=True)

    # ------------------------------------------------------------------
    # Documents
    # ------------------------------------------------------------------

    async def upload_document(
        self,
        collection: str,
        filename: str,
        content_bytes: bytes,
        request: DocumentUploadRequest,
        uploader: str = "",
    ) -> DocumentUploadResponse:
        if not filename.lower().endswith(".md"):
            raise KnowledgeError(
                code=ErrorCode.KB_FORMAT_UNSUPPORTED,
                message=f"Unsupported file format: {filename}",
            )

        try:
            text = content_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            logger.error("kb_file_decode_failed", filename=filename, error=str(exc))
            raise make_error(
                ErrorCode.KB_UPLOAD_FAILED,
                f"Failed to decode file '{filename}'",
            ) from exc

        settings = get_settings()
        max_chunks = settings.embedding.get("max_chunks", 100)
        chunks = self._chunking.chunk(
            text=text,
            doc_id=_doc_id(filename),
            strategy=request.strategy,
            params=request.chunking_params,
            enable_parent_child=request.enable_parent_child,
            parent_params=request.parent_chunk_params,
        )
        if len(chunks) > max_chunks:
            raise KnowledgeError(
                code=ErrorCode.KB_CHUNK_LIMIT_EXCEEDED,
                message=f"Chunk limit exceeded: {len(chunks)} > {max_chunks}",
            )

        task = await self._task_service.submit_task(
            task_type="kb_document_ingest",
            input_data={
                "collection": collection,
                "filename": filename,
                "text": text,
                "doc_type": request.doc_type,
                "source": request.source,
                "tag": request.tag,
                "uploader": uploader,
                "strategy": request.strategy.value,
                "chunking_params": request.chunking_params.model_dump(),
                "enable_parent_child": request.enable_parent_child,
                "parent_chunk_params": request.parent_chunk_params.model_dump(),
            },
            metadata={
                "collection": collection,
                "filename": filename,
                "chunk_count": len(chunks),
            },
        )
        return DocumentUploadResponse(
            task_id=str(task.task_id),
            status="pending",
        )

    async def list_documents(
        self,
        collection: str,
        doc_type: str | None = None,
        source: str | None = None,
        tag: str | None = None,
    ) -> DocumentListResponse:
        if not await self._repo.collection_exists(collection):
            raise KnowledgeError(
                code=ErrorCode.KB_FILE_NOT_FOUND,
                message=f"Collection '{collection}' not found",
            )

        rows = await self._repo.list_documents(
            collection=collection,
            doc_type=doc_type,
            source=source,
            tag=tag,
        )
        items = [
            DocumentListItem(
                doc_id=row["doc_id"],
                doc_type=row.get("doc_type", ""),
                source=row.get("source", ""),
                tag=row.get("tag", ""),
                chunk_count=row.get("chunk_count", 0),
                source_file=row.get("source_file", ""),
            )
            for row in rows
        ]
        return DocumentListResponse(collection=collection, documents=items, total=len(items))

    async def preview_delete_documents(
        self,
        collection: str,
        request: DocumentDeleteRequest,
    ) -> DocumentDeletePreview:
        if not await self._repo.collection_exists(collection):
            raise KnowledgeError(
                code=ErrorCode.KB_FILE_NOT_FOUND,
                message=f"Collection '{collection}' not found",
            )

        filters = _active_filters(request)
        if not filters:
            raise KnowledgeError(
                code=ErrorCode.KB_FILE_NOT_FOUND,
                message="At least one filter is required for deletion preview",
            )

        matched = await self._repo.count_documents_by_filter(
            collection=collection,
            **filters,
        )
        token = _make_confirm_token(collection, filters)
        return DocumentDeletePreview(
            collection=collection,
            matched_count=matched,
            filters=filters,
            confirm_token=token,
        )

    async def delete_documents(
        self,
        collection: str,
        request: DocumentDeleteRequest,
    ) -> DocumentDeleteResponse:
        if not await self._repo.collection_exists(collection):
            raise KnowledgeError(
                code=ErrorCode.KB_FILE_NOT_FOUND,
                message=f"Collection '{collection}' not found",
            )

        filters = _active_filters(request)
        if not filters:
            raise KnowledgeError(
                code=ErrorCode.KB_FILE_NOT_FOUND,
                message="At least one filter is required to delete documents",
            )

        expected_token = _make_confirm_token(collection, filters)
        if not request.confirm_token or not secrets.compare_digest(
            request.confirm_token, expected_token
        ):
            raise KnowledgeError(
                code=ErrorCode.KB_UPLOAD_FAILED,
                message="Invalid or missing confirm_token",
            )

        deleted = await self._repo.delete_documents(
            collection=collection,
            **filters,
        )
        return DocumentDeleteResponse(
            collection=collection,
            deleted_count=deleted,
            confirm_token=expected_token,
        )

    # ------------------------------------------------------------------
    # Ingestion worker (called by task queue)
    # ------------------------------------------------------------------

    async def ingest_document(
        self,
        collection: str,
        filename: str,
        text: str,
        doc_type: str,
        source: str,
        tag: str,
        uploader: str,
        strategy: str,
        chunking_params: dict[str, Any],
        enable_parent_child: bool,
        parent_chunk_params: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute the actual ingestion: chunk, embed, upsert."""
        doc_id = _doc_id(filename)
        params = ChunkingParams(**chunking_params)
        parent_params = ParentChunkParams(**parent_chunk_params)
        chunks = self._chunking.chunk(
            text=text,
            doc_id=doc_id,
            strategy=ChunkingStrategy(strategy),
            params=params,
            enable_parent_child=enable_parent_child,
            parent_params=parent_params,
        )
        if not chunks:
            return {"doc_id": doc_id, "chunk_count": 0}

        texts = [c.text for c in chunks]
        vectors = await self._embedding.embed_batch(texts)
        sparse_vectors = self._embedding.compute_sparse_vectors(texts)

        points: list[Any] = []
        for idx, chunk in enumerate(chunks):
            payload = PointPayload(
                doc_id=doc_id,
                collection=collection,
                doc_type=doc_type,
                source=source,
                tag=tag,
                uploader=uploader,
                heading=chunk.heading,
                heading_level=chunk.heading_level,
                source_file=filename,
                chunk_index=chunk.chunk_index,
                text=chunk.text,
                is_parent=chunk.is_parent,
                parent_id=chunk.parent_id,
            )
            point = self._repo.build_point_insert(
                point_id=chunk.chunk_id,
                vector=vectors[idx],
                sparse_vector=sparse_vectors[idx] or None,
                payload=payload,
            )
            points.append(point)

        written = await self._repo.insert_document_chunks(collection, doc_id, points)
        return {
            "doc_id": doc_id,
            "chunk_count": written,
            "collection": collection,
        }

    # ------------------------------------------------------------------
    # RAG Query
    # ------------------------------------------------------------------

    async def query_rag(self, request: RAGQueryRequest) -> RAGQueryResponse:
        """Execute RAG query synchronously."""
        retrieval_results, citations = await self._retrieve(request)
        if not retrieval_results:
            return RAGQueryResponse(
                content="未找到相关文档，无法回答您的问题。",
                citations=[],
                retrieval_results=[],
                usage=RAGUsage(),
            )

        context = self._assemble_context(retrieval_results)
        content, usage = await self._generate_answer(request, context)
        return RAGQueryResponse(
            content=content,
            citations=citations,
            retrieval_results=retrieval_results,
            usage=usage,
        )

    async def query_rag_stream(
        self,
        request: RAGQueryRequest,
        sse: SSEStreamService,
    ):
        """Execute RAG query with SSE streaming."""
        async for event in sse.start():
            yield event

        retrieval_results, citations = await self._retrieve(request)

        if citations:
            async for event in sse.citation([c.model_dump(mode="json") for c in citations]):
                yield event

        if not retrieval_results:
            async for event in sse.chunk("未找到相关文档，无法回答您的问题。"):
                yield event
            async for event in sse.done():
                yield event
            return

        context = self._assemble_context(retrieval_results)
        llm_request = self._build_llm_request(request, context)

        try:
            gateway = self._resolve_llm_gateway()
            stream = gateway.generate_stream(llm_request)
            async for chunk in stream:
                if chunk.content:
                    async for event in sse.chunk(chunk.content):
                        yield event
            usage = RAGUsage(
                input_tokens=chunk.input_tokens or 0,
                output_tokens=chunk.output_tokens or 0,
                model=llm_request.model or "",
            )
        except Exception as exc:
            logger.error("rag_stream_generation_failed", error=str(exc))
            async for event in sse.error(ErrorCode.RAG_GENERATION_FAILED, "回答生成失败"):
                yield event
            return

        async for event in sse.usage(
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            model=usage.model,
        ):
            yield event

        async for event in sse.done():
            yield event

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _retrieve(
        self,
        request: RAGQueryRequest,
    ) -> tuple[list[RAGRetrievalResult], list[RAGCitation]]:
        """Retrieve relevant chunks across collections."""
        collections = request.collection_names
        if not collections:
            collections = [c.name for c in (await self._repo.list_collections())]

        query_embedding = await self._embedding.embed_batch([request.query])
        query_vector = query_embedding[0] if query_embedding else []
        sparse_vectors = self._embedding.compute_sparse_vectors([request.query])
        sparse_vector = sparse_vectors[0] if sparse_vectors else None

        all_results: list[SearchResult] = []
        for collection in collections:
            if not await self._repo.collection_exists(collection):
                continue
            query_filter = self._build_retrieval_filter(request)
            try:
                results = await self._repo.search_chunks(
                    collection=collection,
                    query_vector=query_vector,
                    sparse_vector=sparse_vector,
                    strategy=request.retrieval_strategy,
                    top_k=request.top_k,
                    score_threshold=request.score_threshold,
                    query_filter=query_filter,
                )
                for r in results:
                    r.payload["_collection"] = collection
                all_results.extend(results)
            except AppError:
                raise
            except Exception as exc:
                logger.warning(
                    "rag_collection_search_failed",
                    collection=collection,
                    error=str(exc),
                )

        if not all_results:
            return [], []

        # Deduplicate by doc_id + chunk_index, keep highest score
        deduped = _deduplicate_results(all_results)

        # Optional rerank
        if request.enable_rerank:
            deduped = self._rerank_results(deduped, request.query)

        # Resolve parent chunks for parent-child mode
        retrieval_results: list[RAGRetrievalResult] = []
        citations: list[RAGCitation] = []
        seen_files: set[str] = set()

        for result in deduped[: request.top_k]:
            payload = result.payload
            collection = payload.get("_collection", "")
            parent_id = payload.get("parent_id")
            parent_text = None
            parent_index = None

            if parent_id:
                parents = await self._repo.get_parent_chunks(
                    collection=collection,
                    parent_ids=[parent_id],
                )
                if parents:
                    parent_text = parents[0].payload.get("text", "")
                    parent_index = parents[0].payload.get("chunk_index", 0)

            retrieval_results.append(
                RAGRetrievalResult(
                    chunk_text=payload.get("text", ""),
                    score=result.score,
                    chunk_index=payload.get("chunk_index", 0),
                    parent_chunk_text=parent_text,
                    parent_chunk_index=parent_index,
                    metadata={
                        "doc_type": payload.get("doc_type", ""),
                        "source": payload.get("source", ""),
                        "tag": payload.get("tag", ""),
                        "source_file": payload.get("source_file", ""),
                    },
                )
            )

            filename = payload.get("source_file", "")
            if filename and filename not in seen_files:
                seen_files.add(filename)
                citations.append(
                    RAGCitation(
                        filename=filename,
                        chunk_text=payload.get("text", ""),
                        score=result.score,
                    )
                )

        return retrieval_results, citations

    def _build_retrieval_filter(
        self, request: RAGQueryRequest
    ) -> dict[str, list[str]] | None:
        filters: dict[str, list[str]] = {}
        if request.doc_type:
            filters["doc_type"] = [request.doc_type]
        if request.source:
            filters["source"] = [request.source]
        if request.tag:
            filters["tag"] = [request.tag]
        if request.uploader:
            filters["uploader"] = [request.uploader]
        return filters or None

    def _assemble_context(self, retrieval_results: list[RAGRetrievalResult]) -> str:
        parts: list[str] = []
        for idx, result in enumerate(retrieval_results, start=1):
            text = result.chunk_text
            if result.parent_chunk_text:
                text = result.parent_chunk_text
            parts.append(f"[Document {idx}]\n{text}\n")
        return "\n".join(parts)

    def _build_llm_request(self, request: RAGQueryRequest, context: str) -> LLMRequest:
        prompts = self._resolve_prompt_manager()
        system_prompt = prompts.render("rag/system", {"context": context})
        user_prompt = prompts.render("rag/user", {"question": request.query})

        messages = [
            Message(role="system", content=system_prompt),
            Message(role="user", content=user_prompt),
        ]

        return LLMRequest(
            messages=messages,
            model=request.model_override,
            task_type="rag_merge",
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            stream=False,
        )

    async def _generate_answer(
        self, request: RAGQueryRequest, context: str
    ) -> tuple[str, RAGUsage]:
        llm_request = self._build_llm_request(request, context)
        try:
            gateway = self._resolve_llm_gateway()
            response = await gateway.generate(llm_request)
            return response.content, RAGUsage(
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                model=response.model,
            )
        except AppError:
            raise
        except Exception as exc:
            logger.error("rag_generation_failed", error=str(exc))
            raise RAGError(
                code=ErrorCode.RAG_GENERATION_FAILED,
                message="回答生成失败",
            ) from exc

    def _rerank_results(
        self, results: list[SearchResult], query: str
    ) -> list[SearchResult]:
        """Simple rerank by boosting exact keyword matches.

        Full cross-encoder reranking can be added later without changing the interface.
        """
        query_terms = set(query.lower().split())
        scored: list[tuple[float, SearchResult]] = []
        for result in results:
            text = result.payload.get("text", "").lower()
            overlap = sum(1 for term in query_terms if term in text)
            # Combine vector score with keyword overlap boost
            boosted = result.score + (overlap * 0.01)
            scored.append((boosted, result))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [r for _, r in scored]

    def _resolve_llm_gateway(self) -> LLMGateway:
        if self._llm is None:
            raise RAGError(
                code=ErrorCode.RAG_GENERATION_FAILED,
                message="LLM Gateway not configured",
            )
        return self._llm

    def _resolve_prompt_manager(self) -> PromptManager:
        if self._prompts is None:
            raise RAGError(
                code=ErrorCode.RAG_GENERATION_FAILED,
                message="Prompt Manager not configured",
            )
        return self._prompts


def _deduplicate_results(results: list[SearchResult]) -> list[SearchResult]:
    """Deduplicate results by doc_id + chunk_index, keeping highest score."""
    best: dict[str, SearchResult] = {}
    for r in results:
        payload = r.payload
        key = f"{payload.get('doc_id', r.id)}:{payload.get('chunk_index', 0)}"
        if key not in best or r.score > best[key].score:
            best[key] = r
    return sorted(best.values(), key=lambda x: x.score, reverse=True)


def _default_payload_indexes() -> list[PayloadIndexConfig]:
    return [
        PayloadIndexConfig(field="doc_type", type="keyword"),
        PayloadIndexConfig(field="source", type="keyword"),
        PayloadIndexConfig(field="tag", type="keyword"),
        PayloadIndexConfig(field="uploader", type="keyword"),
        PayloadIndexConfig(field="doc_id", type="keyword"),
    ]


def _doc_id(filename: str) -> str:
    """Derive a stable document id from filename and current timestamp."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    digest = hashlib.sha256(f"{filename}:{now}:{uuid4()}".encode()).hexdigest()[:16]
    return f"doc:{digest}"


def _active_filters(request: DocumentDeleteRequest) -> dict[str, str]:
    filters: dict[str, str] = {}
    if request.doc_id:
        filters["doc_id"] = request.doc_id
    if request.source:
        filters["source"] = request.source
    if request.tag:
        filters["tag"] = request.tag
    if request.doc_type:
        filters["doc_type"] = request.doc_type
    return filters


def _make_confirm_token(collection: str, filters: dict[str, str]) -> str:
    payload = "|".join(f"{k}={v}" for k, v in sorted(filters.items()))
    raw = f"{collection}:{payload}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]
