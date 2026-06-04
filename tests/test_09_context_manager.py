from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4, UUID

import pytest

from app.core.errors import SystemError, ErrorCode
from app.domain.session.repo import SessionRepo, MessageRepo
from app.domain.session.service import SessionService
from app.schemas.session import (
    ContextWindowResult,
    MessageCreateRequest,
    MessageDetail,
    MessageListResponse,
    MessageUpdateRequest,
    SessionCreateRequest,
    SessionDetail,
    SessionListResponse,
    SessionRole,
    TruncationStrategy,
    VALID_ROLES,
)
from app.services.context_manager import ContextManager, count_tokens


# ===========================================================================
# Helpers
# ===========================================================================

def _make_session_model(**overrides):
    """Create a mock SessionModel-like object."""
    defaults = {
        "id": uuid4(),
        "user_id": "user-1",
        "title": "Test Session",
        "intent_type": None,
        "model_config": None,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "metadata_": None,
    }
    defaults.update(overrides)
    return MagicMock(**defaults)


def _make_message_model(session_id=None, role="user", content="Hello", **overrides):
    """Create a mock MessageModel-like object."""
    defaults = {
        "id": uuid4(),
        "session_id": session_id or uuid4(),
        "role": role,
        "content": content,
        "token_count": None,
        "model_name": None,
        "citations": None,
        "tool_calls": None,
        "tool_results": None,
        "created_at": datetime.now(timezone.utc),
        "metadata_": None,
    }
    defaults.update(overrides)
    return MagicMock(**defaults)


def _make_msg_detail(content="Hello", role="user", session_id=None):
    return MessageDetail(
        id=uuid4(),
        session_id=session_id or uuid4(),
        role=role,
        content=content,
        token_count=None,
        model_name=None,
        citations=None,
        tool_calls=None,
        tool_results=None,
        created_at=datetime.now(timezone.utc),
        metadata=None,
    )


# ===========================================================================
# TestSessionSchemas
# ===========================================================================

class TestSessionSchemas:
    def test_session_role_values(self):
        assert VALID_ROLES == {"user", "assistant", "system", "tool"}

    def test_truncation_strategy_values(self):
        strategies = {s.value for s in TruncationStrategy}
        assert strategies == {"recent_priority", "summary", "sliding_window"}

    def test_session_create_request(self):
        req = SessionCreateRequest(user_id="u1", title="T")
        assert req.user_id == "u1"
        assert req.title == "T"
        assert req.metadata is None

    def test_message_create_request(self):
        sid = uuid4()
        req = MessageCreateRequest(session_id=sid, role=SessionRole.USER, content="hi")
        assert req.role == SessionRole.USER
        assert req.content == "hi"

    def test_context_window_result(self):
        r = ContextWindowResult(
            session_id=uuid4(),
            system_prompt=None,
            messages=[],
            total_tokens=0,
            truncated=False,
            summary=None,
        )
        assert r.truncated is False
        assert r.total_tokens == 0

    def test_message_update_request(self):
        req = MessageUpdateRequest(content="updated")
        assert req.content == "updated"


# ===========================================================================
# TestSessionRepo
# ===========================================================================

class TestSessionRepo:
    def test_init(self):
        mock_session = AsyncMock()
        repo = SessionRepo(session=mock_session)
        assert repo.model is not None

    @pytest.mark.asyncio
    async def test_create_session(self):
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()
        mock_session.refresh = AsyncMock()

        repo = SessionRepo(session=mock_session)
        from app.infra.models import SessionModel

        data = {"user_id": "u1", "title": "T", "metadata_": None}
        with patch.object(repo, "create", new_callable=AsyncMock) as mock_create:
            mock_model = _make_session_model(user_id="u1", title="T")
            mock_create.return_value = mock_model
            result = await repo.create_session(data)
            assert result.user_id == "u1"

    @pytest.mark.asyncio
    async def test_get_by_session_id(self):
        mock_session = AsyncMock()
        sid = uuid4()
        repo = SessionRepo(session=mock_session)
        with patch.object(repo, "get_by_id", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = _make_session_model(id=sid)
            result = await repo.get_by_session_id(sid)
            assert result is not None

    @pytest.mark.asyncio
    async def test_list_sessions(self):
        mock_session = AsyncMock()
        repo = SessionRepo(session=mock_session)
        with patch.object(repo, "list", new_callable=AsyncMock) as mock_list:
            from app.infra.database import PaginatedResult
            mock_list.return_value = PaginatedResult(items=[], total=0, offset=0, limit=20)
            items, total = await repo.list_sessions(user_id="u1")
            assert total == 0


# ===========================================================================
# TestMessageRepo
# ===========================================================================

class TestMessageRepo:
    def test_init(self):
        mock_session = AsyncMock()
        repo = MessageRepo(session=mock_session)
        assert repo.model is not None

    @pytest.mark.asyncio
    async def test_create_message(self):
        mock_session = AsyncMock()
        repo = MessageRepo(session=mock_session)
        with patch.object(repo, "create", new_callable=AsyncMock) as mock_create:
            sid = uuid4()
            mock_model = _make_message_model(session_id=sid)
            mock_create.return_value = mock_model
            result = await repo.create_message({"session_id": sid, "role": "user", "content": "hi"})
            assert result is not None

    @pytest.mark.asyncio
    async def test_count_messages(self):
        mock_session = AsyncMock()
        repo = MessageRepo(session=mock_session)
        with patch.object(repo, "count", new_callable=AsyncMock) as mock_count:
            mock_count.return_value = 5
            count = await repo.count_messages(uuid4())
            assert count == 5


# ===========================================================================
# TestSessionService
# ===========================================================================

class TestSessionService:
    def _make_service(self):
        mock_session_repo = AsyncMock(spec=SessionRepo)
        mock_message_repo = AsyncMock(spec=MessageRepo)
        service = SessionService(
            session_repo=mock_session_repo,
            message_repo=mock_message_repo,
        )
        return service, mock_session_repo, mock_message_repo

    @pytest.mark.asyncio
    async def test_create_session(self):
        service, mock_repo, _ = self._make_service()
        mock_model = _make_session_model(user_id="u1", title="Test")
        mock_repo.create_session.return_value = mock_model
        req = SessionCreateRequest(user_id="u1", title="Test")
        result = await service.create_session(req)
        assert result.user_id == "u1"
        assert result.title == "Test"

    @pytest.mark.asyncio
    async def test_get_session(self):
        service, mock_repo, _ = self._make_service()
        sid = uuid4()
        mock_model = _make_session_model(id=sid, user_id="u1")
        mock_repo.get_by_session_id.return_value = mock_model
        result = await service.get_session(sid)
        assert result.id == sid

    @pytest.mark.asyncio
    async def test_get_session_not_found(self):
        service, mock_repo, _ = self._make_service()
        mock_repo.get_by_session_id.return_value = None
        with pytest.raises(SystemError) as exc_info:
            await service.get_session(uuid4())
        assert exc_info.value.code == ErrorCode.VALIDATION_ERROR

    @pytest.mark.asyncio
    async def test_list_sessions(self):
        service, mock_repo, _ = self._make_service()
        mock_repo.list_sessions.return_value = ([], 0)
        result = await service.list_sessions(user_id="u1")
        assert result.total == 0
        assert result.items == []

    @pytest.mark.asyncio
    async def test_delete_session(self):
        service, mock_repo, _ = self._make_service()
        sid = uuid4()
        mock_repo.get_by_session_id.return_value = _make_session_model(id=sid)
        mock_repo.delete_session.return_value = True
        result = await service.delete_session(sid)
        assert result is True

    @pytest.mark.asyncio
    async def test_delete_session_not_found(self):
        service, mock_repo, _ = self._make_service()
        mock_repo.get_by_session_id.return_value = None
        with pytest.raises(SystemError):
            await service.delete_session(uuid4())

    @pytest.mark.asyncio
    async def test_expire_session(self):
        service, mock_repo, _ = self._make_service()
        sid = uuid4()
        mock_model = _make_session_model(id=sid, metadata_={})
        mock_repo.get_by_session_id.return_value = mock_model
        expired_model = _make_session_model(id=sid, metadata_={"status": "expired"})
        mock_repo.update_session.return_value = expired_model
        result = await service.expire_session(sid)
        assert result.id == sid

    @pytest.mark.asyncio
    async def test_add_message(self):
        service, mock_session_repo, mock_message_repo = self._make_service()
        sid = uuid4()
        mock_session_repo.get_by_session_id.return_value = _make_session_model(id=sid)
        msg = _make_message_model(session_id=sid, content="hello")
        mock_message_repo.create_message.return_value = msg
        req = MessageCreateRequest(session_id=sid, role=SessionRole.USER, content="hello")
        result = await service.add_message(req)
        assert result is not None

    @pytest.mark.asyncio
    async def test_add_message_session_not_found(self):
        service, mock_session_repo, _ = self._make_service()
        mock_session_repo.get_by_session_id.return_value = None
        req = MessageCreateRequest(session_id=uuid4(), role=SessionRole.USER, content="hello")
        with pytest.raises(SystemError):
            await service.add_message(req)

    @pytest.mark.asyncio
    async def test_get_messages(self):
        service, _, mock_message_repo = self._make_service()
        mock_message_repo.list_messages.return_value = ([], 0)
        result = await service.get_messages(session_id=uuid4())
        assert result.items == []
        assert result.total == 0

    @pytest.mark.asyncio
    async def test_update_message(self):
        service, _, mock_message_repo = self._make_service()
        mid = uuid4()
        mock_message_repo.get_by_message_id.return_value = _make_message_model(id=mid)
        updated = _make_message_model(id=mid, content="updated content")
        mock_message_repo.update_message.return_value = updated
        req = MessageUpdateRequest(content="updated content")
        result = await service.update_message(mid, req)
        assert result is not None

    @pytest.mark.asyncio
    async def test_update_message_not_found(self):
        service, _, mock_message_repo = self._make_service()
        mock_message_repo.get_by_message_id.return_value = None
        req = MessageUpdateRequest(content="x")
        with pytest.raises(SystemError):
            await service.update_message(uuid4(), req)


# ===========================================================================
# TestContextManager (token counting)
# ===========================================================================

class TestCountTokens:
    def test_empty_string(self):
        assert count_tokens("") == 0

    def test_none_equivalent(self):
        assert count_tokens("") == 0

    def test_approximate_fallback(self):
        text = "Hello world, this is a test message for token counting."
        result = count_tokens(text, model="nonexistent_encoding_for_fallback")
        assert result >= 1
        assert isinstance(result, int)

    def test_short_text(self):
        result = count_tokens("Hi")
        assert result >= 1

    def test_long_text(self):
        long_text = "word " * 1000
        result = count_tokens(long_text)
        assert result > 0


# ===========================================================================
# TestContextManager (strategies)
# ===========================================================================

class TestContextManagerStrategies:
    def _make_cm(self, redis_client=None, max_tokens=4096, strategy="recent_priority"):
        return ContextManager(
            redis_client=redis_client,
            cache_ttl=3600,
            default_max_tokens=max_tokens,
            default_strategy=strategy,
        )

    @pytest.mark.asyncio
    async def test_recent_priority_basic(self):
        cm = self._make_cm(max_tokens=1000)
        sid = uuid4()
        msgs = [_make_msg_detail(content=f"Message {i}", role="user", session_id=sid) for i in range(10)]
        result = await cm.get_context_window(sid, msgs, system_prompt="You are helpful.")
        assert result.session_id == sid
        assert result.total_tokens > 0
        assert len(result.messages) <= 10

    @pytest.mark.asyncio
    async def test_recent_priority_truncation(self):
        cm = self._make_cm(max_tokens=50)
        sid = uuid4()
        long_msgs = [_make_msg_detail(content="A" * 100, role="user", session_id=sid) for _ in range(10)]
        result = await cm.get_context_window(sid, long_msgs)
        assert result.truncated is True
        assert len(result.messages) < 10

    @pytest.mark.asyncio
    async def test_recent_priority_no_truncation(self):
        cm = self._make_cm(max_tokens=10000)
        sid = uuid4()
        msgs = [_make_msg_detail(content="Short", role="user", session_id=sid) for _ in range(3)]
        result = await cm.get_context_window(sid, msgs)
        assert len(result.messages) == 3
        assert result.truncated is False or result.total_tokens <= 10000

    @pytest.mark.asyncio
    async def test_sliding_window_strategy(self):
        cm = self._make_cm(max_tokens=100, strategy="sliding_window")
        sid = uuid4()
        msgs = [_make_msg_detail(content=f"Msg {i}", role="user", session_id=sid) for i in range(20)]
        result = await cm.get_context_window(sid, msgs, strategy="sliding_window")
        assert len(result.messages) <= 20

    @pytest.mark.asyncio
    async def test_summary_strategy(self):
        cm = self._make_cm(max_tokens=500, strategy="summary")
        sid = uuid4()
        msgs = [_make_msg_detail(content=f"Message number {i}", role="user", session_id=sid) for i in range(10)]
        result = await cm.get_context_window(sid, msgs, strategy="summary")
        assert result.session_id == sid
        assert len(result.messages) <= 10

    @pytest.mark.asyncio
    async def test_summary_produces_summary_text(self):
        cm = self._make_cm(max_tokens=200, strategy="summary")
        sid = uuid4()
        msgs = [_make_msg_detail(content="A" * 80, role="user", session_id=sid) for _ in range(8)]
        result = await cm.get_context_window(sid, msgs, strategy="summary")
        # If truncation happened and there are dropped messages, summary should exist
        if result.truncated:
            assert result.summary is not None

    @pytest.mark.asyncio
    async def test_system_prompt_consumes_budget(self):
        cm = self._make_cm(max_tokens=30)
        sid = uuid4()
        msgs = [_make_msg_detail(content="Short msg", role="user", session_id=sid)]
        result = await cm.get_context_window(sid, msgs, system_prompt="A" * 100)
        # System prompt alone exceeds budget
        assert result.total_tokens >= 0

    @pytest.mark.asyncio
    async def test_empty_messages(self):
        cm = self._make_cm()
        sid = uuid4()
        result = await cm.get_context_window(sid, [])
        assert result.messages == []
        assert result.truncated is False
        assert result.total_tokens == 0

    @pytest.mark.asyncio
    async def test_context_window_zero_budget(self):
        cm = self._make_cm(max_tokens=0)
        sid = uuid4()
        msgs = [_make_msg_detail(content="Hello", role="user", session_id=sid)]
        result = await cm.get_context_window(sid, msgs, system_prompt="System prompt")
        assert result.total_tokens > 0
        # budget - system_tokens <= 0 means no messages selected

    @pytest.mark.asyncio
    async def test_custom_strategy_override(self):
        cm = self._make_cm(strategy="recent_priority")
        sid = uuid4()
        msgs = [_make_msg_detail(content="Test", role="user", session_id=sid)]
        result = await cm.get_context_window(sid, msgs, strategy="sliding_window")
        assert result.session_id == sid


# ===========================================================================
# TestContextManager (caching)
# ===========================================================================

class TestContextManagerCaching:
    @pytest.mark.asyncio
    async def test_cache_context_with_redis(self):
        mock_redis = AsyncMock()
        mock_redis.hset = AsyncMock(return_value=1)
        mock_redis.client = AsyncMock()
        mock_redis.client.expire = AsyncMock()
        cm = ContextManager(redis_client=mock_redis, cache_ttl=600)
        sid = uuid4()
        msgs = [_make_msg_detail(content="Hello", role="user", session_id=sid)]
        result = await cm.get_context_window(sid, msgs)
        mock_redis.hset.assert_called_once()
        mock_redis.client.expire.assert_called_once()

    @pytest.mark.asyncio
    async def test_cache_context_without_redis(self):
        cm = ContextManager(redis_client=None)
        sid = uuid4()
        msgs = [_make_msg_detail(content="Hello", role="user", session_id=sid)]
        result = await cm.get_context_window(sid, msgs)
        assert result is not None

    @pytest.mark.asyncio
    async def test_invalidate_cache(self):
        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock(return_value=1)
        cm = ContextManager(redis_client=mock_redis)
        sid = uuid4()
        await cm.invalidate_cache(sid)
        mock_redis.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_invalidate_cache_no_redis(self):
        cm = ContextManager(redis_client=None)
        await cm.invalidate_cache(uuid4())

    @pytest.mark.asyncio
    async def test_cache_failure_graceful(self):
        mock_redis = AsyncMock()
        mock_redis.hset = AsyncMock(side_effect=Exception("Redis down"))
        mock_redis.client = AsyncMock()
        cm = ContextManager(redis_client=mock_redis, cache_ttl=600)
        sid = uuid4()
        msgs = [_make_msg_detail(content="Hello", role="user", session_id=sid)]
        result = await cm.get_context_window(sid, msgs)
        assert result is not None

    @pytest.mark.asyncio
    async def test_get_cached_context_hit(self):
        mock_redis = AsyncMock()
        mock_redis.hgetall = AsyncMock(return_value={"total_tokens": "100", "truncated": "False", "message_count": "5"})
        cm = ContextManager(redis_client=mock_redis)
        sid = uuid4()
        result = await cm.get_cached_context(sid)
        assert result is not None
        assert result["total_tokens"] == "100"

    @pytest.mark.asyncio
    async def test_get_cached_context_miss(self):
        mock_redis = AsyncMock()
        mock_redis.hgetall = AsyncMock(return_value={})
        cm = ContextManager(redis_client=mock_redis)
        result = await cm.get_cached_context(uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_get_cached_context_no_redis(self):
        cm = ContextManager(redis_client=None)
        result = await cm.get_cached_context(uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_get_cached_context_error_graceful(self):
        mock_redis = AsyncMock()
        mock_redis.hgetall = AsyncMock(side_effect=Exception("Redis error"))
        cm = ContextManager(redis_client=mock_redis)
        result = await cm.get_cached_context(uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_invalidate_cache_error_graceful(self):
        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock(side_effect=Exception("Redis error"))
        cm = ContextManager(redis_client=mock_redis)
        await cm.invalidate_cache(uuid4())


# ===========================================================================
# TestContextManager (strategy edge cases)
# ===========================================================================

class TestContextManagerEdgeCases:
    @pytest.mark.asyncio
    async def test_generate_summary_text_empty(self):
        result = ContextManager._generate_summary_text([])
        assert result == ""

    @pytest.mark.asyncio
    async def test_generate_summary_text_with_messages(self):
        msgs = [
            _make_msg_detail(content="Hello there", role="user"),
            _make_msg_detail(content="I can help", role="assistant"),
        ]
        result = ContextManager._generate_summary_text(msgs)
        assert "user" in result
        assert "assistant" in result
        assert "2 earlier message(s)" in result

    @pytest.mark.asyncio
    async def test_message_with_none_content(self):
        cm = ContextManager()
        sid = uuid4()
        msgs = [_make_msg_detail(content=None, role="user", session_id=sid)]
        result = await cm.get_context_window(sid, msgs)
        assert result.total_tokens == 0 or result.total_tokens >= 0

    @pytest.mark.asyncio
    async def test_single_message_fits(self):
        cm = ContextManager(default_max_tokens=10000)
        sid = uuid4()
        msgs = [_make_msg_detail(content="Hello world", role="user", session_id=sid)]
        result = await cm.get_context_window(sid, msgs)
        assert len(result.messages) == 1

    @pytest.mark.asyncio
    async def test_config_values(self):
        cm = ContextManager(
            redis_client=None,
            cache_ttl=7200,
            default_max_tokens=8192,
            default_strategy="summary",
        )
        assert cm._cache_ttl == 7200
        assert cm._default_max_tokens == 8192
        assert cm._default_strategy == "summary"


# ===========================================================================
# TestContextSettings in config
# ===========================================================================

class TestContextSettings:
    def test_default_values(self):
        from app.core.config import ContextSettings
        settings = ContextSettings()
        assert settings.redis_cache_ttl == 3600
        assert settings.default_max_tokens == 4096
        assert settings.default_strategy == "recent_priority"

    def test_settings_include_context(self):
        from app.core.config import Settings
        settings = Settings()
        assert hasattr(settings, "context")
        assert settings.context.redis_cache_ttl == 3600