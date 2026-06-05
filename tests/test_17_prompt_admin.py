"""Tests for F17: Prompt management API."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.errors import ErrorCode, TaskError
from app.schemas.prompt import (
    PromptResetResponse,
    PromptTemplateDetail,
    PromptTemplateListItem,
    PromptUpdateResponse,
    PromptVersionItem,
    PromptVersionListResponse,
)


# ===========================================================================
# Helpers
# ===========================================================================

def _mock_session_factory():
    """Return a callable that yields an async context manager returning a mock session."""
    class _MockSession:
        async def __aenter__(self):
            return AsyncMock()
        async def __aexit__(self, *args):
            pass
    class _Factory:
        def __call__(self):
            return _MockSession()
    return _Factory()


def _make_detail(name="rag_answer"):
    return PromptTemplateDetail(
        name=name,
        directory="skills",
        description="RAG answer prompt",
        content="You are helpful.\n\nContext: {{context}}\n\nQuery: {{query}}",
        variables=["context", "query"],
        version=3,
        baseline_content="Baseline",
        baseline_version=1,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def _make_list_item(name="rag_answer"):
    return PromptTemplateListItem(
        name=name,
        directory="skills",
        description="RAG answer prompt",
        variables=["context", "query"],
        version=3,
        updated_at=datetime.now(timezone.utc),
    )


# ===========================================================================
# GET /api/v1/prompts
# ===========================================================================

def test_api_list_prompts(monkeypatch):
    """Test GET /api/v1/prompts returns paginated list."""
    from unittest.mock import patch
    from fastapi.testclient import TestClient
    from app.main import app
    from app.core.di import container
    from sqlalchemy.ext.asyncio import async_sessionmaker

    container.register(async_sessionmaker, _mock_session_factory, singleton=True)

    mock_service = MagicMock()
    mock_service.get_template = AsyncMock(return_value=None)  # No exact match
    mock_service.list_templates = AsyncMock(return_value=([
        _make_list_item("rag_answer"),
        _make_list_item("chat_system"),
    ], 2))

    with patch("app.api.v1.prompt._get_prompt_service", return_value=mock_service):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/api/v1/prompts?limit=10&offset=0")

    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 0
    assert len(data["data"]["items"]) == 2
    assert data["data"]["total"] == 2


def test_api_list_prompts_with_directory_filter(monkeypatch):
    """Test GET /api/v1/prompts with directory filter."""
    from unittest.mock import patch
    from fastapi.testclient import TestClient
    from app.main import app
    from app.core.di import container
    from sqlalchemy.ext.asyncio import async_sessionmaker

    container.register(async_sessionmaker, _mock_session_factory, singleton=True)

    mock_service = MagicMock()
    mock_service.get_template = AsyncMock(return_value=None)
    mock_service.list_templates = AsyncMock(return_value=([
        _make_list_item("rag_answer"),
    ], 1))

    with patch("app.api.v1.prompt._get_prompt_service", return_value=mock_service):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/api/v1/prompts?directory=skills")

    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]["items"]) == 1


def test_api_get_prompt_detail_by_name(monkeypatch):
    """Test GET /api/v1/prompts?name=rag_answer returns full detail when exact match."""
    from unittest.mock import patch
    from fastapi.testclient import TestClient
    from app.main import app
    from app.core.di import container
    from sqlalchemy.ext.asyncio import async_sessionmaker

    container.register(async_sessionmaker, _mock_session_factory, singleton=True)

    mock_service = MagicMock()
    mock_service.get_template = AsyncMock(return_value=_make_detail("rag_answer"))

    with patch("app.api.v1.prompt._get_prompt_service", return_value=mock_service):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/api/v1/prompts?name=rag_answer")

    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 0
    assert data["data"]["name"] == "rag_answer"
    assert "content" in data["data"]
    assert data["data"]["content"] == "You are helpful.\n\nContext: {{context}}\n\nQuery: {{query}}"


def test_api_get_prompt_not_found(monkeypatch):
    """Test GET /api/v1/prompts?name=missing returns 404."""
    from unittest.mock import patch
    from fastapi.testclient import TestClient
    from app.main import app
    from app.core.di import container
    from sqlalchemy.ext.asyncio import async_sessionmaker

    container.register(async_sessionmaker, _mock_session_factory, singleton=True)

    mock_service = MagicMock()
    mock_service.get_template = AsyncMock(side_effect=TaskError(
        code=ErrorCode.PROMPT_NOT_FOUND,
        message="Prompt template 'missing' not found",
    ))

    with patch("app.api.v1.prompt._get_prompt_service", return_value=mock_service):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/api/v1/prompts?name=missing")

    data = response.json()
    if isinstance(data, list) and len(data) == 2 and isinstance(data[0], dict):
        data = data[0]
    assert data["code"] == ErrorCode.PROMPT_NOT_FOUND


# ===========================================================================
# PUT /api/v1/prompts/{name}
# ===========================================================================

def test_api_update_prompt_content(monkeypatch):
    """Test PUT /api/v1/prompts/{name} with new content."""
    from unittest.mock import patch
    from fastapi.testclient import TestClient
    from app.main import app
    from app.core.di import container
    from sqlalchemy.ext.asyncio import async_sessionmaker

    container.register(async_sessionmaker, _mock_session_factory, singleton=True)

    mock_service = MagicMock()
    mock_service.update_template = AsyncMock(return_value=PromptUpdateResponse(
        name="rag_answer",
        version=4,
        previous_version=3,
        updated_at=datetime.now(timezone.utc),
    ))

    with patch("app.api.v1.prompt._get_prompt_service", return_value=mock_service):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.put(
            "/api/v1/prompts/rag_answer",
            json={"content": "New content {{query}}"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 0
    assert data["data"]["version"] == 4
    assert data["data"]["previous_version"] == 3


def test_api_update_prompt_rollback(monkeypatch):
    """Test PUT /api/v1/prompts/{name} with rollback_version."""
    from unittest.mock import patch
    from fastapi.testclient import TestClient
    from app.main import app
    from app.core.di import container
    from sqlalchemy.ext.asyncio import async_sessionmaker

    container.register(async_sessionmaker, _mock_session_factory, singleton=True)

    mock_service = MagicMock()
    mock_service.update_template = AsyncMock(return_value=PromptUpdateResponse(
        name="rag_answer",
        version=5,
        previous_version=4,
        updated_at=datetime.now(timezone.utc),
    ))

    with patch("app.api.v1.prompt._get_prompt_service", return_value=mock_service):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.put(
            "/api/v1/prompts/rag_answer",
            json={"rollback_version": 2},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 0
    assert data["data"]["version"] == 5


def test_api_update_prompt_validation_error(monkeypatch):
    """Test PUT /api/v1/prompts/{name} with both content and rollback_version."""
    from unittest.mock import patch
    from fastapi.testclient import TestClient
    from app.main import app
    from app.core.di import container
    from sqlalchemy.ext.asyncio import async_sessionmaker

    container.register(async_sessionmaker, _mock_session_factory, singleton=True)

    mock_service = MagicMock()
    mock_service.update_template = AsyncMock(side_effect=TaskError(
        code=ErrorCode.VALIDATION_ERROR,
        message="Cannot specify both content and rollback_version",
    ))

    with patch("app.api.v1.prompt._get_prompt_service", return_value=mock_service):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.put(
            "/api/v1/prompts/rag_answer",
            json={"content": "New", "rollback_version": 2},
        )

    data = response.json()
    if isinstance(data, list) and len(data) == 2 and isinstance(data[0], dict):
        data = data[0]
    assert data["code"] == ErrorCode.VALIDATION_ERROR


def test_api_update_prompt_not_found(monkeypatch):
    """Test PUT /api/v1/prompts/{name} with non-existent template."""
    from unittest.mock import patch
    from fastapi.testclient import TestClient
    from app.main import app
    from app.core.di import container
    from sqlalchemy.ext.asyncio import async_sessionmaker

    container.register(async_sessionmaker, _mock_session_factory, singleton=True)

    mock_service = MagicMock()
    mock_service.update_template = AsyncMock(side_effect=TaskError(
        code=ErrorCode.PROMPT_NOT_FOUND,
        message="Prompt template 'missing' not found",
    ))

    with patch("app.api.v1.prompt._get_prompt_service", return_value=mock_service):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.put(
            "/api/v1/prompts/missing",
            json={"content": "New content"},
        )

    data = response.json()
    if isinstance(data, list) and len(data) == 2 and isinstance(data[0], dict):
        data = data[0]
    assert data["code"] == ErrorCode.PROMPT_NOT_FOUND


# ===========================================================================
# GET /api/v1/prompts/{name}/versions
# ===========================================================================

def test_api_list_versions(monkeypatch):
    """Test GET /api/v1/prompts/{name}/versions."""
    from unittest.mock import patch
    from fastapi.testclient import TestClient
    from app.main import app
    from app.core.di import container
    from sqlalchemy.ext.asyncio import async_sessionmaker

    container.register(async_sessionmaker, _mock_session_factory, singleton=True)

    mock_service = MagicMock()
    mock_service.get_versions = AsyncMock(return_value=PromptVersionListResponse(
        name="rag_answer",
        current_version=3,
        baseline_version=1,
        versions=[
            PromptVersionItem(version=3, content_preview="Latest content...", description="Latest", updated_by="system"),
            PromptVersionItem(version=2, content_preview="Older content...", description="Previous", updated_by="user1"),
        ],
    ))

    with patch("app.api.v1.prompt._get_prompt_service", return_value=mock_service):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/api/v1/prompts/rag_answer/versions")

    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 0
    assert data["data"]["name"] == "rag_answer"
    assert data["data"]["current_version"] == 3
    assert len(data["data"]["versions"]) == 2


def test_api_list_versions_not_found(monkeypatch):
    """Test GET /api/v1/prompts/{name}/versions with non-existent template."""
    from unittest.mock import patch
    from fastapi.testclient import TestClient
    from app.main import app
    from app.core.di import container
    from sqlalchemy.ext.asyncio import async_sessionmaker

    container.register(async_sessionmaker, _mock_session_factory, singleton=True)

    mock_service = MagicMock()
    mock_service.get_versions = AsyncMock(side_effect=TaskError(
        code=ErrorCode.PROMPT_NOT_FOUND,
        message="Prompt template 'missing' not found",
    ))

    with patch("app.api.v1.prompt._get_prompt_service", return_value=mock_service):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/api/v1/prompts/missing/versions")

    data = response.json()
    if isinstance(data, list) and len(data) == 2 and isinstance(data[0], dict):
        data = data[0]
    assert data["code"] == ErrorCode.PROMPT_NOT_FOUND


# ===========================================================================
# POST /api/v1/prompts/{name}/reset
# ===========================================================================

def test_api_reset_prompt(monkeypatch):
    """Test POST /api/v1/prompts/{name}/reset."""
    from unittest.mock import patch
    from fastapi.testclient import TestClient
    from app.main import app
    from app.core.di import container
    from sqlalchemy.ext.asyncio import async_sessionmaker

    container.register(async_sessionmaker, _mock_session_factory, singleton=True)

    mock_service = MagicMock()
    mock_service.reset_template = AsyncMock(return_value=PromptResetResponse(
        name="rag_answer",
        version=6,
        reset_from_version=5,
        baseline_source="prompts/skills/rag_answer.md",
        updated_at=datetime.now(timezone.utc),
    ))

    with patch("app.api.v1.prompt._get_prompt_service", return_value=mock_service):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post("/api/v1/prompts/rag_answer/reset")

    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 0
    assert data["data"]["version"] == 6
    assert data["data"]["reset_from_version"] == 5
    assert data["data"]["baseline_source"] == "prompts/skills/rag_answer.md"


def test_api_reset_prompt_not_found(monkeypatch):
    """Test POST /api/v1/prompts/{name}/reset with non-existent template."""
    from unittest.mock import patch
    from fastapi.testclient import TestClient
    from app.main import app
    from app.core.di import container
    from sqlalchemy.ext.asyncio import async_sessionmaker

    container.register(async_sessionmaker, _mock_session_factory, singleton=True)

    mock_service = MagicMock()
    mock_service.reset_template = AsyncMock(side_effect=TaskError(
        code=ErrorCode.PROMPT_NOT_FOUND,
        message="Prompt template 'missing' not found",
    ))

    with patch("app.api.v1.prompt._get_prompt_service", return_value=mock_service):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post("/api/v1/prompts/missing/reset")

    data = response.json()
    if isinstance(data, list) and len(data) == 2 and isinstance(data[0], dict):
        data = data[0]
    assert data["code"] == ErrorCode.PROMPT_NOT_FOUND


# ===========================================================================
# Router structure tests
# ===========================================================================

def test_prompt_router_has_prefix():
    from app.api.v1.prompt import router
    assert router.prefix == "/api/v1"
    assert "prompt" in router.tags


def test_prompt_routes_defined():
    from app.api.v1.prompt import router
    routes = [r.path for r in router.routes]
    assert "/api/v1/prompts" in routes
    assert any("/api/v1/prompts/{name}" in r for r in routes)
    assert any("/api/v1/prompts/{name}/versions" in r for r in routes)
    assert any("/api/v1/prompts/{name}/reset" in r for r in routes)
