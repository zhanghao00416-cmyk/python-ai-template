"""F02 tests: Database models, BaseRepo CRUD, Redis client, Alembic migration.

Verification: pytest tests/test_02_database.py
Also: alembic upgrade head (requires running PG/Redis)
"""

from __future__ import annotations

import asyncio
import os
import uuid

import pytest


# ---------------------------------------------------------------------------
# Unit tests — do NOT require PG/Redis running
# ---------------------------------------------------------------------------


class TestModelsImportable:
    """All ORM models can be imported and have correct table names."""

    def test_session_model(self) -> None:
        from app.infra.models import SessionModel
        assert SessionModel.__tablename__ == "sessions"

    def test_message_model(self) -> None:
        from app.infra.models import MessageModel
        assert MessageModel.__tablename__ == "messages"

    def test_task_model(self) -> None:
        from app.infra.models import TaskModel
        assert TaskModel.__tablename__ == "tasks"

    def test_agent_trajectory_model(self) -> None:
        from app.infra.models import AgentTrajectoryModel
        assert AgentTrajectoryModel.__tablename__ == "agent_trajectories"

    def test_prompt_template_model(self) -> None:
        from app.infra.models import PromptTemplateModel
        assert PromptTemplateModel.__tablename__ == "prompt_templates"

    def test_prompt_template_version_model(self) -> None:
        from app.infra.models import PromptTemplateVersionModel
        assert PromptTemplateVersionModel.__tablename__ == "prompt_template_versions"


class TestErrorCodeInfrastructure:
    """12xx infrastructure error codes registered."""

    def test_database_error_code(self) -> None:
        from app.core.errors import ErrorCode
        assert ErrorCode.DATABASE_ERROR == 1201

    def test_qdrant_unavailable_code(self) -> None:
        from app.core.errors import ErrorCode
        assert ErrorCode.QDRANT_UNAVAILABLE == 1202

    def test_redis_error_code(self) -> None:
        from app.core.errors import ErrorCode
        assert ErrorCode.REDIS_ERROR == 1203

    def test_infra_error_class(self) -> None:
        from app.core.errors import InfraError, AppError, ErrorCode
        err = InfraError(ErrorCode.DATABASE_ERROR, "db fail")
        assert isinstance(err, AppError)
        assert err.code == 1201
        assert err.message == "db fail"

    def test_infra_error_http_status(self) -> None:
        from app.core.errors import ErrorCode, InfraError, ERROR_HTTP_STATUS
        assert ERROR_HTTP_STATUS[ErrorCode.DATABASE_ERROR] == 500
        assert ERROR_HTTP_STATUS[ErrorCode.QDRANT_UNAVAILABLE] == 503
        assert ERROR_HTTP_STATUS[ErrorCode.REDIS_ERROR] == 503

    def test_format_parse_error_codes(self) -> None:
        from app.core.errors import format_error_code, parse_error_code
        assert format_error_code(1201) == "AI_1201"
        assert format_error_code(1203) == "AI_1203"
        assert parse_error_code("AI_1201") == 1201
        assert parse_error_code(1203) == 1203


class TestPagination:
    """Pagination class enforces defaults and bounds."""

    def test_defaults(self) -> None:
        from app.infra.database import Pagination
        p = Pagination()
        assert p.offset == 0
        assert p.limit == 20
        assert p.sort_by == "created_at"
        assert p.sort_order == "desc"

    def test_custom_values(self) -> None:
        from app.infra.database import Pagination
        p = Pagination(offset=10, limit=50, sort_by="id", sort_order="asc")
        assert p.offset == 10
        assert p.limit == 50
        assert p.sort_by == "id"
        assert p.sort_order == "asc"

    def test_invalid_sort_order_resets(self) -> None:
        from app.infra.database import Pagination
        p = Pagination(sort_order="invalid")
        assert p.sort_order == "desc"

    def test_negative_offset_clamped(self) -> None:
        from app.infra.database import Pagination
        p = Pagination(offset=-5)
        assert p.offset == 0

    def test_limit_bounds(self) -> None:
        from app.infra.database import Pagination
        p1 = Pagination(limit=0)
        assert p1.limit == 1
        p2 = Pagination(limit=200)
        assert p2.limit == 100


class TestPaginatedResult:
    """PaginatedResult holds items and metadata."""

    def test_to_dict(self) -> None:
        from app.infra.database import PaginatedResult
        pr = PaginatedResult(items=[1, 2, 3], total=100, offset=0, limit=20)
        d = pr.to_dict()
        assert d["total"] == 100
        assert len(d["items"]) == 3
        assert d["offset"] == 0
        assert d["limit"] == 20


class TestBaseRepoModelAccess:
    """BaseRepo stores model class and session correctly."""

    def test_base_repo_init(self) -> None:
        from app.infra.database import BaseRepo
        from app.infra.models import SessionModel

        class FakeSession:
            pass

        repo = BaseRepo(SessionModel, FakeSession())
        assert repo.model is SessionModel
        assert isinstance(repo.session, FakeSession)


class TestRedisClientInit:
    """RedisClient can be instantiated without connecting."""

    def test_redis_client_init(self) -> None:
        from app.infra.redis_client import RedisClient
        client = RedisClient(url="redis://localhost:6379/0")
        assert client._url == "redis://localhost:6379/0"
        assert client._db == 0
        assert client._client is None

    def test_redis_client_access_without_connect_raises(self) -> None:
        from app.infra.redis_client import RedisClient
        from app.core.errors import InfraError, ErrorCode
        client = RedisClient(url="redis://localhost:6379/0")
        with pytest.raises(InfraError) as exc_info:
            _ = client.client
        assert exc_info.value.code == ErrorCode.REDIS_ERROR


class TestDatabaseModuleFunctions:
    """init_db_engine and dispose_engine handle state correctly."""

    def test_get_engine_before_init_raises(self) -> None:
        from app.infra import database as db_mod
        original_engine = db_mod._engine
        original_sf = db_mod._session_factory
        try:
            db_mod._engine = None
            db_mod._session_factory = None
            with pytest.raises(RuntimeError, match="not initialized"):
                db_mod.get_engine()
            with pytest.raises(RuntimeError, match="not initialized"):
                db_mod.get_session_factory()
        finally:
            db_mod._engine = original_engine
            db_mod._session_factory = original_sf


class TestDIIntegration:
    """DI container can register and resolve infra components."""

    def test_register_and_resolve_redis_client_type(self) -> None:
        from app.core.di import DIContainer
        from app.infra.redis_client import RedisClient

        container = DIContainer()
        mock_client = RedisClient(url="redis://fake:6379/0")
        container.register(RedisClient, lambda: mock_client, singleton=True)
        resolved = container.resolve(RedisClient)
        assert resolved is mock_client


class TestAlembicConfig:
    """Alembic migration config is properly set up."""

    def test_alembic_ini_exists(self) -> None:
        import pathlib
        alembic_ini = pathlib.Path(__file__).resolve().parent.parent / "alembic.ini"
        assert alembic_ini.exists()

    def test_migrations_dir_exists(self) -> None:
        import pathlib
        migrations_dir = pathlib.Path(__file__).resolve().parent.parent / "migrations"
        assert migrations_dir.is_dir()
        assert (migrations_dir / "env.py").exists()

    def test_initial_migration_exists(self) -> None:
        import pathlib
        versions_dir = pathlib.Path(__file__).resolve().parent.parent / "migrations" / "versions"
        assert versions_dir.is_dir()
        migration_files = list(versions_dir.glob("*.py"))
        migration_names = [f.stem for f in migration_files if f.name != "__init__.py"]
        assert any("001" in n for n in migration_names)


# ---------------------------------------------------------------------------
# Integration tests — require PG/Redis running (skipped if unavailable)
# ---------------------------------------------------------------------------

_SKIP_MSG = "PG/Redis not available, set TEST_DB_URL and TEST_REDIS_URL to run integration tests"


def _pg_available() -> bool:
    url = os.environ.get("TEST_DB_URL", "")
    if not url:
        return False
    try:
        import asyncio
        from sqlalchemy.ext.asyncio import create_async_engine
        engine = create_async_engine(url)
        async def _check():
            async with engine.connect() as conn:
                from sqlalchemy import text
                await conn.execute(text("SELECT 1"))
            await engine.dispose()
        asyncio.run(_check())
        return True
    except Exception:
        return False


def _redis_available() -> bool:
    url = os.environ.get("TEST_REDIS_URL", "")
    if not url:
        return False
    try:
        import asyncio
        from app.infra.redis_client import RedisClient
        client = RedisClient(url=url)
        asyncio.run(client.connect())
        asyncio.run(client.close())
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _pg_available(), reason=_SKIP_MSG)
class TestBaseRepoCRUD:
    """Integration: BaseRepo CRUD against live PostgreSQL."""

    @pytest.fixture(autouse=True)
    async def setup_db(self):
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
        from app.infra.database import Base
        from app.infra.models import SessionModel

        url = os.environ["TEST_DB_URL"]
        engine = create_async_engine(url)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as session:
            yield session, SessionModel

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()

    async def test_create_and_get_by_id(self, setup_db):
        from app.infra.database import BaseRepo
        session, model = setup_db
        repo = BaseRepo(model, session)

        created = await repo.create({"user_id": "test-user-1", "title": "Test Session"})
        await session.commit()
        assert created.id is not None
        assert created.user_id == "test-user-1"

        fetched = await repo.get_by_id(created.id)
        assert fetched is not None
        assert fetched.user_id == "test-user-1"

    async def test_update(self, setup_db):
        from app.infra.database import BaseRepo
        session, model = setup_db
        repo = BaseRepo(model, session)

        created = await repo.create({"user_id": "test-user-2"})
        await session.commit()

        updated = await repo.update(created.id, {"title": "Updated Title"})
        await session.commit()
        assert updated is not None
        assert updated.title == "Updated Title"

    async def test_delete(self, setup_db):
        from app.infra.database import BaseRepo
        session, model = setup_db
        repo = BaseRepo(model, session)

        created = await repo.create({"user_id": "test-user-3"})
        await session.commit()

        result = await repo.delete(created.id)
        await session.commit()
        assert result is True

        fetched = await repo.get_by_id(created.id)
        assert fetched is None

    async def test_list_with_pagination(self, setup_db):
        from app.infra.database import BaseRepo, Pagination
        session, model = setup_db
        repo = BaseRepo(model, session)

        for i in range(5):
            await repo.create({"user_id": f"list-user-{i}"})
        await session.commit()

        pg = Pagination(offset=0, limit=3, sort_by="created_at", sort_order="asc")
        result = await repo.list(pagination=pg)
        assert len(result.items) <= 3
        assert result.total >= 5

    async def test_count(self, setup_db):
        from app.infra.database import BaseRepo
        session, model = setup_db
        repo = BaseRepo(model, session)

        count_before = await repo.count()
        await repo.create({"user_id": "count-user-1"})
        await session.commit()
        count_after = await repo.count()
        assert count_after == count_before + 1


@pytest.mark.skipif(not _redis_available(), reason=_SKIP_MSG)
class TestRedisIntegration:
    """Integration: RedisClient ping/get/set/delete/incr against live Redis."""

    @pytest.fixture(autouse=True)
    async def setup_redis(self):
        from app.infra.redis_client import RedisClient
        url = os.environ["TEST_REDIS_URL"]
        client = RedisClient(url=url)
        await client.connect()
        yield client
        await client.close()

    async def test_ping(self, setup_redis):
        client = setup_redis
        result = await client.ping()
        assert result is True

    async def test_set_and_get(self, setup_redis):
        client = setup_redis
        key = f"test:f02:setget:{uuid.uuid4()}"
        await client.set(key, "hello", ex=60)
        value = await client.get(key)
        assert value == "hello"

    async def test_delete(self, setup_redis):
        client = setup_redis
        key = f"test:f02:del:{uuid.uuid4()}"
        await client.set(key, "to-delete", ex=60)
        result = await client.delete(key)
        assert result >= 1
        assert await client.get(key) is None

    async def test_incr(self, setup_redis):
        client = setup_redis
        key = f"test:f02:incr:{uuid.uuid4()}"
        val = await client.incr(key)
        assert val == 1
        val = await client.incr(key)
        assert val == 2
        await client.delete(key)


class TestDatabaseModuleExports:
    """Infra __init__ exports key symbols."""

    def test_infra_exports_database(self) -> None:
        from app.infra import Base, BaseRepo, Pagination, PaginatedResult, init_db_engine, get_engine, get_session_factory, get_session, dispose_engine
        assert Base is not None
        assert BaseRepo is not None

    def test_infra_exports_redis(self) -> None:
        from app.infra import RedisClient
        assert RedisClient is not None

    def test_infra_exports_models(self) -> None:
        from app.infra import SessionModel, MessageModel, TaskModel, AgentTrajectoryModel, PromptTemplateModel, PromptTemplateVersionModel
        assert SessionModel.__tablename__ == "sessions"
        assert MessageModel.__tablename__ == "messages"
        assert TaskModel.__tablename__ == "tasks"