"""Knowledge base API routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Query, UploadFile

from app.api.deps import get_db_session, get_knowledge_service
from app.core.constants import API_PREFIX
from app.core.context import request_id_var, trace_id_var
from app.core.errors import ErrorCode, KnowledgeError, make_error
from app.core.response import error_response, error_to_status, ok_response
from app.schemas.knowledge import (
    CollectionCreateRequest,
    DocumentDeleteRequest,
    DocumentUploadRequest,
    RAGQueryRequest,
)

router = APIRouter(prefix=API_PREFIX, tags=["knowledge"])


# ------------------------------------------------------------------
# Collections
# ------------------------------------------------------------------

@router.post("/kb/collections")
async def create_collection(
    request: CollectionCreateRequest,
    session=Depends(get_db_session),
):
    rid = request_id_var.get() or ""
    tid = trace_id_var.get() or ""
    service = get_knowledge_service(session)
    try:
        result = await service.create_collection(request)
        return ok_response(data=result.model_dump(mode="json"), request_id=rid, trace_id=tid)
    except KnowledgeError as exc:
        return error_response(exc, request_id=rid, trace_id=tid), error_to_status(exc)
    except Exception as exc:
        err = make_error(ErrorCode.INTERNAL_ERROR, str(exc))
        return error_response(err, request_id=rid, trace_id=tid), error_to_status(err)


@router.get("/kb/collections")
async def list_collections(
    session=Depends(get_db_session),
):
    rid = request_id_var.get() or ""
    tid = trace_id_var.get() or ""
    service = get_knowledge_service(session)
    try:
        result = await service.list_collections()
        return ok_response(data=result.model_dump(mode="json"), request_id=rid, trace_id=tid)
    except Exception as exc:
        err = make_error(ErrorCode.INTERNAL_ERROR, str(exc))
        return error_response(err, request_id=rid, trace_id=tid), error_to_status(err)


@router.delete("/kb/collections/{collection_name}")
async def delete_collection(
    collection_name: str,
    session=Depends(get_db_session),
):
    rid = request_id_var.get() or ""
    tid = trace_id_var.get() or ""
    service = get_knowledge_service(session)
    try:
        result = await service.delete_collection(collection_name)
        return ok_response(data=result.model_dump(mode="json"), request_id=rid, trace_id=tid)
    except KnowledgeError as exc:
        return error_response(exc, request_id=rid, trace_id=tid), error_to_status(exc)
    except Exception as exc:
        err = make_error(ErrorCode.INTERNAL_ERROR, str(exc))
        return error_response(err, request_id=rid, trace_id=tid), error_to_status(err)


# ------------------------------------------------------------------
# Documents
# ------------------------------------------------------------------

@router.post("/kb/collections/{collection_name}/documents")
async def upload_document(
    collection_name: str,
    doc_type: str = Query(default="article", min_length=1, max_length=64),
    source: str = Query(default="", max_length=256),
    tag: str = Query(default="", max_length=256),
    strategy: str = Query(default="fixed_overlap"),
    chunk_size: int = Query(default=500, ge=50, le=4000),
    chunk_overlap: int = Query(default=50, ge=0, le=1000),
    delimiter: str | None = Query(default=None),
    enable_parent_child: bool = Query(default=False),
    parent_chunk_size: int = Query(default=1000, ge=100, le=8000),
    parent_chunk_overlap: int = Query(default=100, ge=0, le=2000),
    file: UploadFile = File(...),
    session=Depends(get_db_session),
):
    rid = request_id_var.get() or ""
    tid = trace_id_var.get() or ""
    service = get_knowledge_service(session)
    try:
        request_model = DocumentUploadRequest(
            doc_type=doc_type,
            source=source,
            tag=tag,
            strategy=strategy,  # type: ignore[arg-type]
            chunking_params={  # type: ignore[arg-type]
                "chunk_size": chunk_size,
                "chunk_overlap": chunk_overlap,
                "delimiter": delimiter,
            },
            enable_parent_child=enable_parent_child,
            parent_chunk_params={  # type: ignore[arg-type]
                "chunk_size": parent_chunk_size,
                "chunk_overlap": parent_chunk_overlap,
            },
        )
        content = await file.read()
        result = await service.upload_document(
            collection=collection_name,
            filename=file.filename or "unnamed.md",
            content_bytes=content,
            request=request_model,
        )
        return ok_response(data=result.model_dump(mode="json"), request_id=rid, trace_id=tid)
    except KnowledgeError as exc:
        return error_response(exc, request_id=rid, trace_id=tid), error_to_status(exc)
    except Exception as exc:
        err = make_error(ErrorCode.KB_UPLOAD_FAILED, str(exc))
        return error_response(err, request_id=rid, trace_id=tid), error_to_status(err)


@router.get("/kb/collections/{collection_name}/documents")
async def list_documents(
    collection_name: str,
    doc_type: str | None = Query(None),
    source: str | None = Query(None),
    tag: str | None = Query(None),
    session=Depends(get_db_session),
):
    rid = request_id_var.get() or ""
    tid = trace_id_var.get() or ""
    service = get_knowledge_service(session)
    try:
        result = await service.list_documents(
            collection=collection_name,
            doc_type=doc_type,
            source=source,
            tag=tag,
        )
        return ok_response(data=result.model_dump(mode="json"), request_id=rid, trace_id=tid)
    except KnowledgeError as exc:
        return error_response(exc, request_id=rid, trace_id=tid), error_to_status(exc)
    except Exception as exc:
        err = make_error(ErrorCode.INTERNAL_ERROR, str(exc))
        return error_response(err, request_id=rid, trace_id=tid), error_to_status(err)


@router.delete("/kb/collections/{collection_name}/documents")
async def delete_documents(
    collection_name: str,
    doc_id: str | None = Query(None),
    source: str | None = Query(None),
    tag: str | None = Query(None),
    doc_type: str | None = Query(None),
    confirm_token: str | None = Query(None),
    session=Depends(get_db_session),
):
    rid = request_id_var.get() or ""
    tid = trace_id_var.get() or ""
    service = get_knowledge_service(session)
    request_model = DocumentDeleteRequest(
        doc_id=doc_id,
        source=source,
        tag=tag,
        doc_type=doc_type,
        confirm_token=confirm_token,
    )
    try:
        if not confirm_token:
            result = await service.preview_delete_documents(
                collection=collection_name,
                request=request_model,
            )
        else:
            result = await service.delete_documents(
                collection=collection_name,
                request=request_model,
            )
        return ok_response(data=result.model_dump(mode="json"), request_id=rid, trace_id=tid)
    except KnowledgeError as exc:
        return error_response(exc, request_id=rid, trace_id=tid), error_to_status(exc)
    except Exception as exc:
        err = make_error(ErrorCode.INTERNAL_ERROR, str(exc))
        return error_response(err, request_id=rid, trace_id=tid), error_to_status(err)


# ------------------------------------------------------------------
# RAG Query
# ------------------------------------------------------------------

@router.post("/kb/query")
async def query_rag(
    request: RAGQueryRequest,
    session=Depends(get_db_session),
):
    rid = request_id_var.get() or ""
    tid = trace_id_var.get() or ""
    service = get_knowledge_service(session)
    try:
        if request.stream:
            from fastapi.responses import StreamingResponse
            from app.services.sse_stream import SSEStreamService, wrap_with_heartbeat

            async def is_disconnected() -> bool:
                return False

            sse = SSEStreamService(
                intent="qa",
                user_id=request.user_id,
                session_id=request.session_id or "",
                is_disconnected=is_disconnected,
            )

            async def event_generator():
                async for event in service.query_rag_stream(request, sse):
                    yield event

            wrapped = wrap_with_heartbeat(event_generator(), sse)
            return StreamingResponse(
                wrapped,
                media_type="text/event-stream",
            )
        else:
            result = await service.query_rag(request)
            return ok_response(
                data=result.model_dump(mode="json"),
                request_id=rid,
                trace_id=tid,
            )
    except KnowledgeError as exc:
        return error_response(exc, request_id=rid, trace_id=tid), error_to_status(exc)
    except Exception as exc:
        err = make_error(ErrorCode.RAG_RETRIEVAL_FAILED, str(exc))
        return error_response(err, request_id=rid, trace_id=tid), error_to_status(err)
