"""Intent classification API routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session
from app.core.constants import API_PREFIX
from app.core.context import request_id_var, trace_id_var
from app.core.errors import ErrorCode, IntentError, make_error
from app.core.response import error_response, error_to_status, ok_response
from app.domain.intent.service import IntentDomainService
from app.schemas.intent import IntentRequest, IntentResponse
from app.services.llm.gateway import LLMGateway
from app.services.prompt_manager import PromptManager

router = APIRouter(prefix=API_PREFIX, tags=["intent"])


def _get_intent_service() -> IntentDomainService:
    """Factory to create IntentDomainService with DI dependencies."""
    llm_gateway = _resolve_llm_gateway()
    prompt_manager = _resolve_prompt_manager()
    return IntentDomainService(
        llm_gateway=llm_gateway,
        prompt_manager=prompt_manager,
    )


def _resolve_llm_gateway() -> LLMGateway:
    from app.core.di import container
    try:
        return container.resolve(LLMGateway)
    except Exception as exc:
        raise IntentError(
            code=ErrorCode.INTENT_CLASSIFY_FAILED,
            message="LLM Gateway not available",
        ) from exc


def _resolve_prompt_manager() -> PromptManager:
    from app.core.di import container
    try:
        return container.resolve(PromptManager)
    except Exception as exc:
        raise IntentError(
            code=ErrorCode.INTENT_CLASSIFY_FAILED,
            message="Prompt Manager not available",
        ) from exc


@router.post("/intent")
async def classify_intent(
    request: IntentRequest,
    session: AsyncSession = Depends(get_db_session),
):
    """Classify user intent using the three-layer funnel."""
    rid = request_id_var.get() or ""
    tid = trace_id_var.get() or ""
    service = _get_intent_service()

    try:
        result = await service.classify(
            query=request.query,
            candidates=request.candidates,
            options={
                "keyword_enabled": request.options.keyword_enabled,
                "similarity_enabled": request.options.similarity_enabled,
                "multi_intent_enabled": request.options.multi_intent_enabled,
            },
        )
        return ok_response(data=result.model_dump(mode="json"), request_id=rid, trace_id=tid)
    except IntentError as exc:
        return error_response(exc, request_id=rid, trace_id=tid), error_to_status(exc)
    except Exception as exc:
        err = make_error(ErrorCode.INTENT_CLASSIFY_FAILED, str(exc))
        return error_response(err, request_id=rid, trace_id=tid), error_to_status(err)
