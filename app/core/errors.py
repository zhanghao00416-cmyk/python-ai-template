"""Application errors.

Canonical formats (see docs/01-architecture/ERROR_CODE.md):
- REST JSON ``code``: int (e.g. 2003; success is 0)
- SSE error event ``code``: str ``AI_%04d`` (e.g. ``AI_2003``)
- ``AppError.code``: int, same as REST

Registry and lookup added by F03.
"""

from __future__ import annotations

from enum import IntEnum
from typing import Any


def format_error_code(code: int) -> str:
    """Format integer code for SSE/logs (2003 -> 'AI_2003')."""
    return f"AI_{code:04d}"


def parse_error_code(value: str | int) -> int:
    """Parse REST/SSE code to integer ('AI_2003' or 2003 -> 2003)."""
    if isinstance(value, int):
        return value
    s = value.strip().upper()
    if s.startswith("AI_"):
        s = s[3:]
    return int(s)


# ---------------------------------------------------------------------------
# 0xxx — System / Infrastructure
# ---------------------------------------------------------------------------
ERROR_CODE_INTERNAL = 1
ERROR_CODE_CONFIG = 2
ERROR_CODE_SERVICE_UNAVAILABLE = 3
ERROR_CODE_TIMEOUT = 4
ERROR_CODE_VALIDATION = 5
ERROR_CODE_RATE_LIMITED = 6
ERROR_CODE_DEPENDENCY = 7

# 1xxx — Auth
ERROR_CODE_AUTH_INVALID_KEY = 1001
ERROR_CODE_AUTH_EXPIRED_KEY = 1002
ERROR_CODE_AUTH_FORBIDDEN = 1003
ERROR_CODE_AUTH_RATE_LIMITED = 1004
ERROR_CODE_AUTH_BODY_TOO_LARGE = 1005

# 11xx — Model Gateway
ERROR_CODE_MODEL_TIMEOUT = 1101
ERROR_CODE_LOCAL_MODEL_UNAVAILABLE = 1102
ERROR_CODE_MODEL_FORMAT_ERROR = 1103
ERROR_CODE_CLOUD_MODEL_ERROR = 1104

# 12xx — Infrastructure
ERROR_CODE_DATABASE_ERROR = 1201
ERROR_CODE_QDRANT_UNAVAILABLE = 1202
ERROR_CODE_REDIS_ERROR = 1203

# 2xxx — Intent
ERROR_CODE_INTENT_CLASSIFY_FAILED = 2001
ERROR_CODE_INTENT_UNKNOWN = 2002
ERROR_CODE_INTENT_TIMEOUT = 2003
ERROR_CODE_INTENT_INVALID_INPUT = 2004

# 3xxx — RAG
ERROR_CODE_RAG_COLLECTION_NOT_FOUND = 3001
ERROR_CODE_RAG_RETRIEVAL_FAILED = 3002
ERROR_CODE_RAG_NO_RESULTS = 3003
ERROR_CODE_RAG_GENERATION_FAILED = 3004
ERROR_CODE_RAG_INDEXING_FAILED = 3005
ERROR_CODE_RAG_DOCUMENT_NOT_FOUND = 3006
ERROR_CODE_RAG_RERANK_NOT_ENABLED = 3007

# 4xxx — Multimodal
ERROR_CODE_MULTIMODAL_INVALID_INPUT = 4001
ERROR_CODE_MULTIMODAL_PROCESSING_FAILED = 4002

# 6xxx — Knowledge
ERROR_CODE_KB_UPLOAD_FAILED = 6001
ERROR_CODE_KB_FILENAME_EXISTS = 6002
ERROR_CODE_KB_FILE_NOT_FOUND = 6003
ERROR_CODE_KB_FORMAT_UNSUPPORTED = 6004
ERROR_CODE_KB_VECTOR_WRITE_FAILED = 6005
ERROR_CODE_KB_CHUNK_LIMIT_EXCEEDED = 6006

# 7xxx — Agent
ERROR_CODE_AGENT_STATE_INVALID = 7001
ERROR_CODE_AGENT_TOOL_NOT_FOUND = 7002
ERROR_CODE_AGENT_EXECUTION_FAILED = 7003
ERROR_CODE_AGENT_MAX_ITERATIONS = 7004
ERROR_CODE_AGENT_ORCHESTRATION_FAILED = 7005

# 8xxx — Workflow
ERROR_CODE_WORKFLOW_NODE_NOT_FOUND = 8001
ERROR_CODE_WORKFLOW_EDGE_INVALID = 8002
ERROR_CODE_WORKFLOW_EXECUTION_FAILED = 8003
ERROR_CODE_WORKFLOW_CYCLE_DETECTED = 8004
ERROR_CODE_WORKFLOW_STATE_ERROR = 8005

# 9xxx — Task / Prompt / SSE
ERROR_CODE_TASK_NOT_FOUND = 9001
ERROR_CODE_TASK_ALREADY_RUNNING = 9002
ERROR_CODE_TASK_SUBMIT_FAILED = 9003
ERROR_CODE_PROMPT_NOT_FOUND = 9004
ERROR_CODE_PROMPT_PATH_INVALID = 9005
ERROR_CODE_PROMPT_WRITE_FAILED = 9006
ERROR_CODE_SSE_CONNECTION_LOST = 9007


class ErrorCode(IntEnum):
    # 0xxx — System
    INTERNAL_ERROR = ERROR_CODE_INTERNAL
    CONFIG_ERROR = ERROR_CODE_CONFIG
    SERVICE_UNAVAILABLE = ERROR_CODE_SERVICE_UNAVAILABLE
    TIMEOUT_ERROR = ERROR_CODE_TIMEOUT
    VALIDATION_ERROR = ERROR_CODE_VALIDATION
    RATE_LIMITED = ERROR_CODE_RATE_LIMITED
    DEPENDENCY_ERROR = ERROR_CODE_DEPENDENCY

    # 1xxx — Auth
    AUTH_INVALID_KEY = ERROR_CODE_AUTH_INVALID_KEY
    AUTH_EXPIRED_KEY = ERROR_CODE_AUTH_EXPIRED_KEY
    AUTH_FORBIDDEN = ERROR_CODE_AUTH_FORBIDDEN
    AUTH_RATE_LIMITED = ERROR_CODE_AUTH_RATE_LIMITED
    AUTH_BODY_TOO_LARGE = ERROR_CODE_AUTH_BODY_TOO_LARGE

    # 11xx — Model Gateway
    MODEL_TIMEOUT = ERROR_CODE_MODEL_TIMEOUT
    LOCAL_MODEL_UNAVAILABLE = ERROR_CODE_LOCAL_MODEL_UNAVAILABLE
    MODEL_FORMAT_ERROR = ERROR_CODE_MODEL_FORMAT_ERROR
    CLOUD_MODEL_ERROR = ERROR_CODE_CLOUD_MODEL_ERROR

    # 12xx — Infrastructure
    DATABASE_ERROR = ERROR_CODE_DATABASE_ERROR
    QDRANT_UNAVAILABLE = ERROR_CODE_QDRANT_UNAVAILABLE
    REDIS_ERROR = ERROR_CODE_REDIS_ERROR

    # 2xxx — Intent
    INTENT_CLASSIFY_FAILED = ERROR_CODE_INTENT_CLASSIFY_FAILED
    INTENT_UNKNOWN = ERROR_CODE_INTENT_UNKNOWN
    INTENT_TIMEOUT = ERROR_CODE_INTENT_TIMEOUT
    INTENT_INVALID_INPUT = ERROR_CODE_INTENT_INVALID_INPUT

    # 3xxx — RAG
    RAG_COLLECTION_NOT_FOUND = ERROR_CODE_RAG_COLLECTION_NOT_FOUND
    RAG_RETRIEVAL_FAILED = ERROR_CODE_RAG_RETRIEVAL_FAILED
    RAG_NO_RESULTS = ERROR_CODE_RAG_NO_RESULTS
    RAG_GENERATION_FAILED = ERROR_CODE_RAG_GENERATION_FAILED
    RAG_INDEXING_FAILED = ERROR_CODE_RAG_INDEXING_FAILED
    RAG_DOCUMENT_NOT_FOUND = ERROR_CODE_RAG_DOCUMENT_NOT_FOUND
    RAG_RERANK_NOT_ENABLED = ERROR_CODE_RAG_RERANK_NOT_ENABLED

    # 4xxx — Multimodal
    MULTIMODAL_INVALID_INPUT = ERROR_CODE_MULTIMODAL_INVALID_INPUT
    MULTIMODAL_PROCESSING_FAILED = ERROR_CODE_MULTIMODAL_PROCESSING_FAILED

    # 6xxx — Knowledge
    KB_UPLOAD_FAILED = ERROR_CODE_KB_UPLOAD_FAILED
    KB_FILENAME_EXISTS = ERROR_CODE_KB_FILENAME_EXISTS
    KB_FILE_NOT_FOUND = ERROR_CODE_KB_FILE_NOT_FOUND
    KB_FORMAT_UNSUPPORTED = ERROR_CODE_KB_FORMAT_UNSUPPORTED
    KB_VECTOR_WRITE_FAILED = ERROR_CODE_KB_VECTOR_WRITE_FAILED
    KB_CHUNK_LIMIT_EXCEEDED = ERROR_CODE_KB_CHUNK_LIMIT_EXCEEDED

    # 7xxx — Agent
    AGENT_STATE_INVALID = ERROR_CODE_AGENT_STATE_INVALID
    AGENT_TOOL_NOT_FOUND = ERROR_CODE_AGENT_TOOL_NOT_FOUND
    AGENT_EXECUTION_FAILED = ERROR_CODE_AGENT_EXECUTION_FAILED
    AGENT_MAX_ITERATIONS = ERROR_CODE_AGENT_MAX_ITERATIONS
    AGENT_ORCHESTRATION_FAILED = ERROR_CODE_AGENT_ORCHESTRATION_FAILED

    # 8xxx — Workflow
    WORKFLOW_NODE_NOT_FOUND = ERROR_CODE_WORKFLOW_NODE_NOT_FOUND
    WORKFLOW_EDGE_INVALID = ERROR_CODE_WORKFLOW_EDGE_INVALID
    WORKFLOW_EXECUTION_FAILED = ERROR_CODE_WORKFLOW_EXECUTION_FAILED
    WORKFLOW_CYCLE_DETECTED = ERROR_CODE_WORKFLOW_CYCLE_DETECTED
    WORKFLOW_STATE_ERROR = ERROR_CODE_WORKFLOW_STATE_ERROR

    # 9xxx — Task / Prompt / SSE
    TASK_NOT_FOUND = ERROR_CODE_TASK_NOT_FOUND
    TASK_ALREADY_RUNNING = ERROR_CODE_TASK_ALREADY_RUNNING
    TASK_SUBMIT_FAILED = ERROR_CODE_TASK_SUBMIT_FAILED
    PROMPT_NOT_FOUND = ERROR_CODE_PROMPT_NOT_FOUND
    PROMPT_PATH_INVALID = ERROR_CODE_PROMPT_PATH_INVALID
    PROMPT_WRITE_FAILED = ERROR_CODE_PROMPT_WRITE_FAILED
    SSE_CONNECTION_LOST = ERROR_CODE_SSE_CONNECTION_LOST


# ---------------------------------------------------------------------------
# Error HTTP status mapping
# ---------------------------------------------------------------------------
ERROR_HTTP_STATUS: dict[int, int] = {
    # 0xxx
    ErrorCode.INTERNAL_ERROR: 500,
    ErrorCode.CONFIG_ERROR: 500,
    ErrorCode.SERVICE_UNAVAILABLE: 503,
    ErrorCode.TIMEOUT_ERROR: 504,
    ErrorCode.VALIDATION_ERROR: 400,
    ErrorCode.RATE_LIMITED: 429,
    ErrorCode.DEPENDENCY_ERROR: 502,
    # 1xxx
    ErrorCode.AUTH_INVALID_KEY: 401,
    ErrorCode.AUTH_EXPIRED_KEY: 401,
    ErrorCode.AUTH_FORBIDDEN: 403,
    ErrorCode.AUTH_RATE_LIMITED: 429,
    ErrorCode.AUTH_BODY_TOO_LARGE: 413,
    # 11xx
    ErrorCode.MODEL_TIMEOUT: 504,
    ErrorCode.LOCAL_MODEL_UNAVAILABLE: 503,
    ErrorCode.MODEL_FORMAT_ERROR: 502,
    ErrorCode.CLOUD_MODEL_ERROR: 503,
    # 12xx
    ErrorCode.DATABASE_ERROR: 500,
    ErrorCode.QDRANT_UNAVAILABLE: 503,
    ErrorCode.REDIS_ERROR: 503,
    # 2xxx
    ErrorCode.INTENT_CLASSIFY_FAILED: 500,
    ErrorCode.INTENT_UNKNOWN: 400,
    ErrorCode.INTENT_TIMEOUT: 504,
    ErrorCode.INTENT_INVALID_INPUT: 400,
    # 3xxx
    ErrorCode.RAG_COLLECTION_NOT_FOUND: 404,
    ErrorCode.RAG_RETRIEVAL_FAILED: 400,
    ErrorCode.RAG_NO_RESULTS: 200,
    ErrorCode.RAG_GENERATION_FAILED: 500,
    ErrorCode.RAG_INDEXING_FAILED: 500,
    ErrorCode.RAG_DOCUMENT_NOT_FOUND: 404,
    ErrorCode.RAG_RERANK_NOT_ENABLED: 400,
    # 4xxx
    ErrorCode.MULTIMODAL_INVALID_INPUT: 400,
    ErrorCode.MULTIMODAL_PROCESSING_FAILED: 500,
    # 6xxx
    ErrorCode.KB_UPLOAD_FAILED: 500,
    ErrorCode.KB_FILENAME_EXISTS: 409,
    ErrorCode.KB_FILE_NOT_FOUND: 404,
    ErrorCode.KB_FORMAT_UNSUPPORTED: 415,
    ErrorCode.KB_VECTOR_WRITE_FAILED: 500,
    ErrorCode.KB_CHUNK_LIMIT_EXCEEDED: 413,
    # 7xxx
    ErrorCode.AGENT_STATE_INVALID: 400,
    ErrorCode.AGENT_TOOL_NOT_FOUND: 404,
    ErrorCode.AGENT_EXECUTION_FAILED: 500,
    ErrorCode.AGENT_MAX_ITERATIONS: 500,
    ErrorCode.AGENT_ORCHESTRATION_FAILED: 500,
    # 8xxx
    ErrorCode.WORKFLOW_NODE_NOT_FOUND: 404,
    ErrorCode.WORKFLOW_EDGE_INVALID: 400,
    ErrorCode.WORKFLOW_EXECUTION_FAILED: 500,
    ErrorCode.WORKFLOW_CYCLE_DETECTED: 400,
    ErrorCode.WORKFLOW_STATE_ERROR: 400,
    # 9xxx
    ErrorCode.TASK_NOT_FOUND: 404,
    ErrorCode.TASK_ALREADY_RUNNING: 409,
    ErrorCode.TASK_SUBMIT_FAILED: 500,
    ErrorCode.PROMPT_NOT_FOUND: 404,
    ErrorCode.PROMPT_PATH_INVALID: 400,
    ErrorCode.PROMPT_WRITE_FAILED: 500,
    ErrorCode.SSE_CONNECTION_LOST: 200,
}


# ---------------------------------------------------------------------------
# Error description registry
# ---------------------------------------------------------------------------
ERROR_DESCRIPTIONS: dict[int, str] = {
    ErrorCode.INTERNAL_ERROR: "Internal error",
    ErrorCode.CONFIG_ERROR: "Configuration error",
    ErrorCode.SERVICE_UNAVAILABLE: "Service unavailable",
    ErrorCode.TIMEOUT_ERROR: "Operation timed out",
    ErrorCode.VALIDATION_ERROR: "Validation error",
    ErrorCode.RATE_LIMITED: "Rate limited",
    ErrorCode.DEPENDENCY_ERROR: "External dependency error",
    ErrorCode.AUTH_INVALID_KEY: "Invalid or missing API key",
    ErrorCode.AUTH_EXPIRED_KEY: "Expired API key",
    ErrorCode.AUTH_FORBIDDEN: "Permission denied",
    ErrorCode.AUTH_RATE_LIMITED: "API key rate limited",
    ErrorCode.AUTH_BODY_TOO_LARGE: "Request body too large",
    ErrorCode.MODEL_TIMEOUT: "Model call timed out",
    ErrorCode.LOCAL_MODEL_UNAVAILABLE: "Local model service unavailable",
    ErrorCode.MODEL_FORMAT_ERROR: "Model returned malformed response",
    ErrorCode.CLOUD_MODEL_ERROR: "Cloud model API call failed",
    ErrorCode.DATABASE_ERROR: "Database connection or query failed",
    ErrorCode.QDRANT_UNAVAILABLE: "Qdrant connection failed",
    ErrorCode.REDIS_ERROR: "Redis connection or operation failed",
    ErrorCode.INTENT_CLASSIFY_FAILED: "Intent classification failed",
    ErrorCode.INTENT_UNKNOWN: "Unknown or missing intent",
    ErrorCode.INTENT_TIMEOUT: "Intent classification timed out",
    ErrorCode.INTENT_INVALID_INPUT: "Invalid input for intent classification",
    ErrorCode.RAG_COLLECTION_NOT_FOUND: "Requested collection not found",
    ErrorCode.RAG_RETRIEVAL_FAILED: "Retrieval query failed",
    ErrorCode.RAG_NO_RESULTS: "No relevant documents found",
    ErrorCode.RAG_GENERATION_FAILED: "Answer generation failed",
    ErrorCode.RAG_INDEXING_FAILED: "Document indexing failed",
    ErrorCode.RAG_DOCUMENT_NOT_FOUND: "Requested document not found",
    ErrorCode.RAG_RERANK_NOT_ENABLED: "Reranking requested but not enabled",
    ErrorCode.MULTIMODAL_INVALID_INPUT: "Invalid or unreachable multimodal input",
    ErrorCode.MULTIMODAL_PROCESSING_FAILED: "Multimodal processing failed",
    ErrorCode.KB_UPLOAD_FAILED: "File upload failed",
    ErrorCode.KB_FILENAME_EXISTS: "Filename already exists",
    ErrorCode.KB_FILE_NOT_FOUND: "File not found",
    ErrorCode.KB_FORMAT_UNSUPPORTED: "Unsupported file format",
    ErrorCode.KB_VECTOR_WRITE_FAILED: "Vector write failed",
    ErrorCode.KB_CHUNK_LIMIT_EXCEEDED: "Chunk count exceeds limit",
    ErrorCode.AGENT_STATE_INVALID: "Invalid agent state transition",
    ErrorCode.AGENT_TOOL_NOT_FOUND: "Referenced tool not registered",
    ErrorCode.AGENT_EXECUTION_FAILED: "Agent execution loop failed",
    ErrorCode.AGENT_MAX_ITERATIONS: "Agent exceeded maximum iterations",
    ErrorCode.AGENT_ORCHESTRATION_FAILED: "Multi-agent orchestration failed",
    ErrorCode.WORKFLOW_NODE_NOT_FOUND: "Referenced node not found",
    ErrorCode.WORKFLOW_EDGE_INVALID: "Invalid conditional edge configuration",
    ErrorCode.WORKFLOW_EXECUTION_FAILED: "Workflow execution failed",
    ErrorCode.WORKFLOW_CYCLE_DETECTED: "Workflow DAG contains a cycle",
    ErrorCode.WORKFLOW_STATE_ERROR: "Invalid workflow state transition",
    ErrorCode.TASK_NOT_FOUND: "Referenced task not found",
    ErrorCode.TASK_ALREADY_RUNNING: "Task already in running state",
    ErrorCode.TASK_SUBMIT_FAILED: "Failed to submit task to queue",
    ErrorCode.PROMPT_NOT_FOUND: "Prompt template file not found",
    ErrorCode.PROMPT_PATH_INVALID: "Prompt path contains invalid characters",
    ErrorCode.PROMPT_WRITE_FAILED: "Failed to write prompt template",
    ErrorCode.SSE_CONNECTION_LOST: "SSE client disconnected",
}


# ---------------------------------------------------------------------------
# Exception classes
# ---------------------------------------------------------------------------
class AppError(Exception):
    code: int = ERROR_CODE_INTERNAL

    def __init__(self, code: int, message: str, *, detail: str | None = None) -> None:
        self.code = code
        self.message = message
        self.detail = detail
        super().__init__(message)


class SystemError(AppError):
    pass


class AuthError(AppError):
    pass


class IntentError(AppError):
    pass


class RAGError(AppError):
    pass


class MultimodalError(AppError):
    pass


class KnowledgeError(AppError):
    pass


class AgentError(AppError):
    pass


class WorkflowError(AppError):
    pass


class TaskError(AppError):
    pass


class InfraError(AppError):
    pass


# Removed placeholders: VisionError, VideoError replaced by MultimodalError
# per ERROR_CODE.md 4xxx domain


# ---------------------------------------------------------------------------
# Centralized lookup functions (F03)
# ---------------------------------------------------------------------------
def get_http_status(code: int) -> int:
    """Get HTTP status code for an error code. Defaults to 500."""
    return ERROR_HTTP_STATUS.get(code, 500)


def get_error_description(code: int) -> str:
    """Get default English description for an error code."""
    return ERROR_DESCRIPTIONS.get(code, "Unknown error")


def is_known_code(code: int) -> bool:
    """Check if an integer code is registered in ErrorCode."""
    return code in ErrorCode._value2member_map_


def make_error(code: int, message: str | None = None, *, detail: str | None = None) -> AppError:
    """Create an AppError with the correct domain subclass based on code range."""
    domain_map: list[tuple[range, type[AppError]]] = [
        (range(0, 1000), SystemError),
        (range(1100, 1200), SystemError),
        (range(1200, 1300), InfraError),
        (range(1000, 1100), AuthError),
        (range(2000, 3000), IntentError),
        (range(3000, 4000), RAGError),
        (range(4000, 5000), MultimodalError),
        (range(6000, 7000), KnowledgeError),
        (range(7000, 8000), AgentError),
        (range(8000, 9000), WorkflowError),
        (range(9000, 10000), TaskError),
    ]

    msg = message or get_error_description(code)
    for code_range, exc_cls in domain_map:
        if code in code_range:
            return exc_cls(code, msg, detail=detail)
    return AppError(code, msg, detail=detail)