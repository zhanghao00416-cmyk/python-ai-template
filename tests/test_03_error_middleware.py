"""F03 tests: Error system, unified response, TraceMiddleware, ExceptionMiddleware.

Verification: pytest tests/test_03_error_middleware.py
"""

from __future__ import annotations

import json
import pytest
from fastapi.testclient import TestClient


def _create_client() -> TestClient:
    from app.main import app
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# ErrorCode registry & lookup
# ---------------------------------------------------------------------------


class TestErrorCodeRegistry:
    """All domain codes are registered and lookup functions work."""

    def test_all_zeroxxx_system_codes(self) -> None:
        from app.core.errors import ErrorCode
        assert ErrorCode.INTERNAL_ERROR == 1
        assert ErrorCode.CONFIG_ERROR == 2
        assert ErrorCode.SERVICE_UNAVAILABLE == 3
        assert ErrorCode.TIMEOUT_ERROR == 4
        assert ErrorCode.VALIDATION_ERROR == 5
        assert ErrorCode.RATE_LIMITED == 6
        assert ErrorCode.DEPENDENCY_ERROR == 7

    def test_all_1xxx_auth_codes(self) -> None:
        from app.core.errors import ErrorCode
        assert ErrorCode.AUTH_INVALID_KEY == 1001
        assert ErrorCode.AUTH_EXPIRED_KEY == 1002
        assert ErrorCode.AUTH_FORBIDDEN == 1003
        assert ErrorCode.AUTH_RATE_LIMITED == 1004
        assert ErrorCode.AUTH_BODY_TOO_LARGE == 1005

    def test_all_11xx_model_gateway_codes(self) -> None:
        from app.core.errors import ErrorCode
        assert ErrorCode.MODEL_TIMEOUT == 1101
        assert ErrorCode.LOCAL_MODEL_UNAVAILABLE == 1102
        assert ErrorCode.MODEL_FORMAT_ERROR == 1103
        assert ErrorCode.CLOUD_MODEL_ERROR == 1104

    def test_all_12xx_infra_codes(self) -> None:
        from app.core.errors import ErrorCode
        assert ErrorCode.DATABASE_ERROR == 1201
        assert ErrorCode.QDRANT_UNAVAILABLE == 1202
        assert ErrorCode.REDIS_ERROR == 1203

    def test_all_2xxx_intent_codes(self) -> None:
        from app.core.errors import ErrorCode
        assert ErrorCode.INTENT_CLASSIFY_FAILED == 2001
        assert ErrorCode.INTENT_UNKNOWN == 2002
        assert ErrorCode.INTENT_TIMEOUT == 2003
        assert ErrorCode.INTENT_INVALID_INPUT == 2004

    def test_all_3xxx_rag_codes(self) -> None:
        from app.core.errors import ErrorCode
        assert ErrorCode.RAG_COLLECTION_NOT_FOUND == 3001
        assert ErrorCode.RAG_RETRIEVAL_FAILED == 3002
        assert ErrorCode.RAG_NO_RESULTS == 3003
        assert ErrorCode.RAG_GENERATION_FAILED == 3004
        assert ErrorCode.RAG_INDEXING_FAILED == 3005
        assert ErrorCode.RAG_DOCUMENT_NOT_FOUND == 3006
        assert ErrorCode.RAG_RERANK_NOT_ENABLED == 3007

    def test_all_4xxx_multimodal_codes(self) -> None:
        from app.core.errors import ErrorCode
        assert ErrorCode.MULTIMODAL_INVALID_INPUT == 4001
        assert ErrorCode.MULTIMODAL_PROCESSING_FAILED == 4002

    def test_all_6xxx_knowledge_codes(self) -> None:
        from app.core.errors import ErrorCode
        assert ErrorCode.KB_UPLOAD_FAILED == 6001
        assert ErrorCode.KB_FILENAME_EXISTS == 6002
        assert ErrorCode.KB_FILE_NOT_FOUND == 6003
        assert ErrorCode.KB_FORMAT_UNSUPPORTED == 6004
        assert ErrorCode.KB_VECTOR_WRITE_FAILED == 6005
        assert ErrorCode.KB_CHUNK_LIMIT_EXCEEDED == 6006

    def test_all_7xxx_agent_codes(self) -> None:
        from app.core.errors import ErrorCode
        assert ErrorCode.AGENT_STATE_INVALID == 7001
        assert ErrorCode.AGENT_TOOL_NOT_FOUND == 7002
        assert ErrorCode.AGENT_EXECUTION_FAILED == 7003
        assert ErrorCode.AGENT_MAX_ITERATIONS == 7004
        assert ErrorCode.AGENT_ORCHESTRATION_FAILED == 7005

    def test_all_8xxx_workflow_codes(self) -> None:
        from app.core.errors import ErrorCode
        assert ErrorCode.WORKFLOW_NODE_NOT_FOUND == 8001
        assert ErrorCode.WORKFLOW_EDGE_INVALID == 8002
        assert ErrorCode.WORKFLOW_EXECUTION_FAILED == 8003
        assert ErrorCode.WORKFLOW_CYCLE_DETECTED == 8004
        assert ErrorCode.WORKFLOW_STATE_ERROR == 8005

    def test_all_9xxx_task_codes(self) -> None:
        from app.core.errors import ErrorCode
        assert ErrorCode.TASK_NOT_FOUND == 9001
        assert ErrorCode.TASK_ALREADY_RUNNING == 9002
        assert ErrorCode.TASK_SUBMIT_FAILED == 9003
        assert ErrorCode.PROMPT_NOT_FOUND == 9004
        assert ErrorCode.PROMPT_PATH_INVALID == 9005
        assert ErrorCode.PROMPT_WRITE_FAILED == 9006
        assert ErrorCode.SSE_CONNECTION_LOST == 9007


class TestFormatParse:
    """format_error_code and parse_error_code work correctly."""

    def test_format_4_digit(self) -> None:
        from app.core.errors import format_error_code
        assert format_error_code(1) == "AI_0001"
        assert format_error_code(2003) == "AI_2003"
        assert format_error_code(1201) == "AI_1201"

    def test_parse_from_string(self) -> None:
        from app.core.errors import parse_error_code
        assert parse_error_code("AI_2003") == 2003
        assert parse_error_code("AI_0001") == 1
        assert parse_error_code("2003") == 2003

    def test_parse_from_int(self) -> None:
        from app.core.errors import parse_error_code
        assert parse_error_code(2003) == 2003
        assert parse_error_code(1) == 1

    def test_roundtrip(self) -> None:
        from app.core.errors import format_error_code, parse_error_code
        for code in [1, 5, 1001, 2003, 3001, 7001]:
            assert parse_error_code(format_error_code(code)) == code


class TestLookupFunctions:
    """get_http_status, get_error_description, is_known_code, make_error."""

    def test_get_http_status_known(self) -> None:
        from app.core.errors import get_http_status
        assert get_http_status(1) == 500
        assert get_http_status(5) == 400
        assert get_http_status(1001) == 401
        assert get_http_status(3001) == 404

    def test_get_http_status_unknown_defaults_500(self) -> None:
        from app.core.errors import get_http_status
        assert get_http_status(99999) == 500

    def test_get_error_description(self) -> None:
        from app.core.errors import get_error_description
        assert "Internal error" in get_error_description(1)
        assert "Unknown" in get_error_description(99999)

    def test_is_known_code(self) -> None:
        from app.core.errors import is_known_code
        assert is_known_code(1) is True
        assert is_known_code(2003) is True
        assert is_known_code(99999) is False

    def test_make_error_system(self) -> None:
        from app.core.errors import make_error, SystemError
        err = make_error(1, "test")
        assert isinstance(err, SystemError)
        assert err.code == 1

    def test_make_error_auth(self) -> None:
        from app.core.errors import make_error, AuthError
        err = make_error(1001, "bad key")
        assert isinstance(err, AuthError)

    def test_make_error_intent(self) -> None:
        from app.core.errors import make_error, IntentError
        err = make_error(2003, "timeout")
        assert isinstance(err, IntentError)

    def test_make_error_rag(self) -> None:
        from app.core.errors import make_error, RAGError
        err = make_error(3001)
        assert isinstance(err, RAGError)

    def test_make_error_multimodal(self) -> None:
        from app.core.errors import make_error, MultimodalError
        err = make_error(4001)
        assert isinstance(err, MultimodalError)

    def test_make_error_knowledge(self) -> None:
        from app.core.errors import make_error, KnowledgeError
        err = make_error(6001)
        assert isinstance(err, KnowledgeError)

    def test_make_error_agent(self) -> None:
        from app.core.errors import make_error, AgentError
        err = make_error(7001)
        assert isinstance(err, AgentError)

    def test_make_error_workflow(self) -> None:
        from app.core.errors import make_error, WorkflowError
        err = make_error(8001)
        assert isinstance(err, WorkflowError)

    def test_make_error_task(self) -> None:
        from app.core.errors import make_error, TaskError
        err = make_error(9001)
        assert isinstance(err, TaskError)

    def test_make_error_infra(self) -> None:
        from app.core.errors import make_error, InfraError
        err = make_error(1201)
        assert isinstance(err, InfraError)

    def test_make_error_unknown_domain(self) -> None:
        from app.core.errors import make_error, AppError
        err = make_error(5000)
        assert isinstance(err, AppError)
        assert err.code == 5000

    def test_make_error_with_detail(self) -> None:
        from app.core.errors import make_error
        err = make_error(5, "validation", detail="field X is required")
        assert err.detail == "field X is required"


class TestErrorHierarchy:
    """AppError subclass hierarchy."""

    def test_app_error_is_base(self) -> None:
        from app.core.errors import AppError, SystemError, AuthError, IntentError, RAGError
        from app.core.errors import MultimodalError, KnowledgeError, AgentError, WorkflowError, TaskError, InfraError
        for cls in [SystemError, AuthError, IntentError, RAGError, MultimodalError,
                     KnowledgeError, AgentError, WorkflowError, TaskError, InfraError]:
            err = cls(1, "test")
            assert isinstance(err, AppError)


class TestResponseHelpers:
    """Unified response helpers."""

    def test_ok_response(self) -> None:
        from app.core.response import ok_response
        r = ok_response(data={"key": "val"}, request_id="r1", trace_id="t1")
        assert r["code"] == 0
        assert r["data"]["key"] == "val"

    def test_error_response_with_detail(self) -> None:
        from app.core.errors import AppError
        from app.core.response import error_response
        err = AppError(2003, "intent timeout", detail="LLM took too long")
        r = error_response(err, request_id="r1", trace_id="t1")
        assert r["code"] == 2003
        assert r["detail"] == "LLM took too long"

    def test_error_response_without_detail(self) -> None:
        from app.core.errors import SystemError
        from app.core.response import error_response
        err = SystemError(1, "internal error")
        r = error_response(err, request_id="r2", trace_id="t2")
        assert "detail" not in r
        assert r["code"] == 1

    def test_validation_error_response_with_detail(self) -> None:
        from app.core.response import validation_error_response
        r = validation_error_response("field required", request_id="r3", trace_id="t3", detail="name is missing")
        assert r["code"] == 5
        assert r["detail"] == "name is missing"

    def test_validation_error_response_without_detail(self) -> None:
        from app.core.response import validation_error_response
        r = validation_error_response("bad input", request_id="r4", trace_id="t4")
        assert "detail" not in r


# ---------------------------------------------------------------------------
# TraceMiddleware / ExceptionMiddleware integration
# ---------------------------------------------------------------------------


class TestTraceMiddleware:
    """TraceMiddleware injects trace_id and request_id."""

    def test_trace_id_set_from_header(self) -> None:
        from app.core.context import trace_id_var, request_id_var
        client = _create_client()
        response = client.get(
            "/api/v1/health",
            headers={"X-Trace-Id": "trace-abc", "X-Request-Id": "req-123"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["trace_id"] == "trace-abc"
        assert data["request_id"] == "req-123"

    def test_response_headers_contain_ids(self) -> None:
        client = _create_client()
        response = client.get(
            "/api/v1/health",
            headers={"X-Trace-Id": "trace-xyz", "X-Request-Id": "req-456"},
        )
        assert "x-request-id" in response.headers
        assert "x-trace-id" in response.headers
        assert response.headers["x-request-id"] == "req-456"
        assert response.headers["x-trace-id"] == "trace-xyz"

    def test_auto_generate_ids_when_missing(self) -> None:
        client = _create_client()
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["trace_id"] != ""
        assert data["request_id"] != ""
        assert "x-request-id" in response.headers


class TestExceptionMiddleware:
    """ExceptionMiddleware catches errors and returns structured JSON."""

    def test_app_error_returns_structured_json(self) -> None:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.core.errors import IntentError, ErrorCode
        from app.middleware.trace import TraceMiddleware
        from app.middleware.exception import exception_handler_middleware

        app = FastAPI()
        app.add_middleware(TraceMiddleware)
        app.middleware("http")(exception_handler_middleware)

        @app.get("/test-intent-error")
        async def intent_error():
            raise IntentError(ErrorCode.INTENT_CLASSIFY_FAILED, "LLM failed")

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/test-intent-error")
        assert response.status_code == 500
        data = response.json()
        assert data["code"] == 2001
        assert "LLM failed" in data["message"]
        assert "request_id" in data
        assert "trace_id" in data

    def test_validation_error_returns_422(self) -> None:
        """FastAPI wraps Pydantic ValidationError into 422 by default."""
        from fastapi import FastAPI
        from pydantic import BaseModel
        from fastapi.testclient import TestClient
        from app.middleware.trace import TraceMiddleware
        from app.middleware.exception import exception_handler_middleware

        app = FastAPI()
        app.add_middleware(TraceMiddleware)
        app.middleware("http")(exception_handler_middleware)

        class Item(BaseModel):
            name: str
            count: int

        @app.post("/test-validation")
        async def validation_endpoint(item: Item):
            return item

        client = TestClient(app, raise_server_exceptions=False)
        response = client.post("/test-validation", json={"name": "test"})
        assert response.status_code == 422

    def test_unhandled_exception_returns_500(self) -> None:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.middleware.trace import TraceMiddleware
        from app.middleware.exception import exception_handler_middleware

        app = FastAPI()
        app.add_middleware(TraceMiddleware)
        app.middleware("http")(exception_handler_middleware)

        @app.get("/test-unhandled")
        async def unhandled_error():
            raise RuntimeError("something broke")

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/test-unhandled")
        assert response.status_code == 500
        data = response.json()
        assert data["code"] == 1
        assert "Internal" in data["message"]
        assert "request_id" in data
        assert "trace_id" in data

    def test_rest_error_code_is_integer(self) -> None:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.core.errors import SystemError, ErrorCode
        from app.middleware.trace import TraceMiddleware
        from app.middleware.exception import exception_handler_middleware

        app = FastAPI()
        app.add_middleware(TraceMiddleware)
        app.middleware("http")(exception_handler_middleware)

        @app.get("/test-integer-code")
        async def integer_code():
            raise SystemError(ErrorCode.SERVICE_UNAVAILABLE, "service down")

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/test-integer-code")
        data = response.json()
        assert isinstance(data["code"], int)
        assert data["code"] == 3

    def test_auth_error_returns_401(self) -> None:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.core.errors import AuthError, ErrorCode
        from app.middleware.trace import TraceMiddleware
        from app.middleware.exception import exception_handler_middleware

        app = FastAPI()
        app.add_middleware(TraceMiddleware)
        app.middleware("http")(exception_handler_middleware)

        @app.get("/test-auth-error")
        async def auth_error():
            raise AuthError(ErrorCode.AUTH_INVALID_KEY, "bad key")

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/test-auth-error")
        assert response.status_code == 401
        data = response.json()
        assert data["code"] == 1001

    def test_error_with_detail_passed_through(self) -> None:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.core.errors import KnowledgeError
        from app.middleware.trace import TraceMiddleware
        from app.middleware.exception import exception_handler_middleware

        app = FastAPI()
        app.add_middleware(TraceMiddleware)
        app.middleware("http")(exception_handler_middleware)

        @app.get("/test-detail")
        async def detail_error():
            raise KnowledgeError(6001, "upload failed", detail="file too large")

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/test-detail")
        data = response.json()
        assert data["code"] == 6001
        assert data["detail"] == "file too large"

    def test_trace_ids_in_error_response(self) -> None:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.core.errors import RAGError, ErrorCode
        from app.middleware.trace import TraceMiddleware
        from app.middleware.exception import exception_handler_middleware

        app = FastAPI()
        app.add_middleware(TraceMiddleware)
        app.middleware("http")(exception_handler_middleware)

        @app.get("/test-trace-ids")
        async def trace_error():
            raise RAGError(ErrorCode.RAG_COLLECTION_NOT_FOUND, "collection missing")

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/test-trace-ids",
            headers={"X-Trace-Id": "trace-999", "X-Request-Id": "req-888"},
        )
        data = response.json()
        assert data["trace_id"] == "trace-999"
        assert data["request_id"] == "req-888"


class TestErrorHTTPStatusMapping:
    """ERROR_HTTP_STATUS covers all registered codes with correct HTTP status."""

    def test_all_error_codes_have_http_status(self) -> None:
        from app.core.errors import ErrorCode, ERROR_HTTP_STATUS
        for code in ErrorCode:
            assert code.value in ERROR_HTTP_STATUS, f"{code.name} ({code.value}) missing from ERROR_HTTP_STATUS"

    def test_specific_status_codes(self) -> None:
        from app.core.errors import ErrorCode, ERROR_HTTP_STATUS
        assert ERROR_HTTP_STATUS[ErrorCode.INTERNAL_ERROR] == 500
        assert ERROR_HTTP_STATUS[ErrorCode.VALIDATION_ERROR] == 400
        assert ERROR_HTTP_STATUS[ErrorCode.AUTH_INVALID_KEY] == 401
        assert ERROR_HTTP_STATUS[ErrorCode.AUTH_FORBIDDEN] == 403
        assert ERROR_HTTP_STATUS[ErrorCode.RATE_LIMITED] == 429
        assert ERROR_HTTP_STATUS[ErrorCode.SERVICE_UNAVAILABLE] == 503