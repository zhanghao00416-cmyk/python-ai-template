from __future__ import annotations

import time
from contextlib import asynccontextmanager
from typing import Any

import structlog

from app.core.config import get_settings
from app.core.di import container
from app.core.logging import setup_logging, get_logger

logger = get_logger("bootstrap")

_start_time: float = 0.0

_redis_client: Any | None = None
_vector_store: Any | None = None


async def startup() -> None:
    global _start_time
    _start_time = time.monotonic()

    settings = get_settings()
    setup_logging(level=settings.logging.level, log_format=settings.logging.format)
    logger.info("bootstrap.startup_begin")

    try:
        await _init_infra(settings)
    except Exception as exc:
        logger.error("bootstrap.infra_failed", error=str(exc))

    await _register_services()
    logger.info("bootstrap.startup_complete")


async def shutdown() -> None:
    logger.info("bootstrap.shutdown_begin")
    await _shutdown_mcp()
    await _shutdown_infra()
    container.cleanup()
    logger.info("bootstrap.shutdown_complete")


async def _init_infra(settings: Any) -> None:
    health: dict[str, Any] = {}

    try:
        from app.infra.database import init_db_engine, get_engine

        engine = init_db_engine()
        container.register(type(engine), lambda e=engine: e, singleton=True)

        from app.infra.database import get_session_factory

        sf = get_session_factory()
        container.register(type(sf), lambda s=sf: s, singleton=True)

        async with engine.begin() as conn:
            import sqlalchemy
            await conn.execute(sqlalchemy.text("SELECT 1"))
        health["database"] = "ok"
        logger.info("bootstrap.database_ok")
    except Exception as exc:
        health["database"] = "error"
        logger.warning("bootstrap.database_failed", error=str(exc))

    try:
        from app.infra.redis_client import RedisClient

        global _redis_client
        _redis_client = RedisClient(url=settings.redis.url)
        await _redis_client.connect()
        container.register(RedisClient, lambda c=_redis_client: c, singleton=True)
        health["redis"] = "ok"
        logger.info("bootstrap.redis_ok")
    except Exception as exc:
        health["redis"] = "degraded"
        logger.warning("bootstrap.redis_failed", error=str(exc))

    try:
        from app.infra.vector_store import QdrantVectorStore, VectorStoreBase

        global _vector_store
        _vector_store = QdrantVectorStore()
        container.register(VectorStoreBase, lambda v=_vector_store: v, singleton=True)
        container.register(QdrantVectorStore, lambda v=_vector_store: v, singleton=True)
        health["qdrant"] = "ok"
        logger.info("bootstrap.qdrant_ok")
    except Exception as exc:
        health["qdrant"] = "degraded"
        logger.warning("bootstrap.qdrant_init_failed", error=str(exc))

    try:
        from app.services.embedding import EmbeddingService

        embedding_svc = EmbeddingService()
        container.register(EmbeddingService, lambda e=embedding_svc: e, singleton=True)
        logger.info("bootstrap.embedding_service_registered")
    except Exception as exc:
        logger.warning("bootstrap.embedding_service_failed", error=str(exc))

    try:
        await _init_qdrant_collections(settings)
    except Exception as exc:
        logger.warning("bootstrap.qdrant_collections_init_failed", error=str(exc))

    _seed_prompt_defaults(settings)
    _preload_prompts(settings)

    container.register(dict, lambda h=health: h, singleton=False)


async def _init_qdrant_collections(settings: Any) -> None:
    from app.infra.vector_store import VectorStoreBase, CollectionConfig
    from app.schemas.vector_store import PayloadIndexConfig

    vector_store = container.resolve(VectorStoreBase) if VectorStoreBase in container._factories else None
    if vector_store is None:
        global _vector_store
        vector_store = _vector_store
        if vector_store is None:
            logger.warning("bootstrap.qdrant_collections_skipped_no_store")
            return

    collections_cfg = settings.knowledge.collections if hasattr(settings, 'knowledge') else []
    if not collections_cfg:
        logger.info("bootstrap.qdrant_no_collections_configured")
        return

    for coll_cfg in collections_cfg:
        payload_indexes = [
            PayloadIndexConfig(field=idx.get("field", ""), type=idx.get("type", "keyword"))
            for idx in coll_cfg.get("payload_indexes", [])
        ]
        config = CollectionConfig(
            name=coll_cfg.get("name", ""),
            description=coll_cfg.get("description", ""),
            vector_dim=coll_cfg.get("vector_dim", 1024),
            distance=coll_cfg.get("distance", "Cosine"),
            sparse_vector=coll_cfg.get("sparse_vector", True),
            payload_indexes=payload_indexes,
            default_chunk_size=coll_cfg.get("default_chunk_size", 500),
            default_chunk_overlap=coll_cfg.get("default_chunk_overlap", 50),
        )
        try:
            await vector_store.create_collection(config)
            logger.info("bootstrap.qdrant_collection_ensured", name=config.name)
        except Exception as exc:
            logger.warning(
                "bootstrap.qdrant_collection_ensure_failed",
                name=config.name,
                error=str(exc),
            )


async def _shutdown_infra() -> None:
    global _redis_client, _vector_store

    try:
        from app.infra.database import dispose_engine
        await dispose_engine()
        logger.info("bootstrap.database_disposed")
    except Exception as exc:
        logger.warning("bootstrap.database_dispose_failed", error=str(exc))

    if _redis_client is not None:
        try:
            await _redis_client.close()
            logger.info("bootstrap.redis_closed")
        except Exception as exc:
            logger.warning("bootstrap.redis_close_failed", error=str(exc))
        _redis_client = None

    if _vector_store is not None:
        try:
            await _vector_store.close()
            logger.info("bootstrap.vector_store_closed")
        except Exception as exc:
            logger.warning("bootstrap.vector_store_close_failed", error=str(exc))
        _vector_store = None

    try:
        from app.services.embedding import EmbeddingService

        emb_svc = container.resolve(EmbeddingService)
        if emb_svc is not None and hasattr(emb_svc, "close"):
            await emb_svc.close()
            logger.info("bootstrap.embedding_service_closed")
    except Exception as exc:
        logger.warning("bootstrap.embedding_service_close_failed", error=str(exc))


def _seed_prompt_defaults(settings: Any) -> None:
    from app.services.prompt_manager import PromptManager

    pm = PromptManager()
    results = pm.seed_defaults()
    if results:
        logger.info("bootstrap.prompt_seeds", **results)


def _preload_prompts(settings: Any) -> None:
    from app.services.prompt_manager import PromptManager

    pm = PromptManager()
    count = pm.preload()
    container.register(PromptManager, lambda p=pm: p, singleton=True)
    logger.info("bootstrap.prompts_preloaded", count=count)


def _load_skills(skill_registry: Any) -> int:
    """Load all skill YAML files from the skills/ directory."""
    from pathlib import Path

    skills_dir = Path("skills")
    if not skills_dir.is_dir():
        logger.info("bootstrap.skills_dir_missing")
        return 0

    count = 0
    for yaml_file in sorted(skills_dir.glob("*.yaml")):
        if yaml_file.name.startswith("_"):
            continue  # skip _schema.yaml
        try:
            skill_registry.load_from_yaml(str(yaml_file))
            count += 1
        except Exception as exc:
            logger.warning(
                "bootstrap.skill_load_failed",
                file=str(yaml_file),
                error=str(exc),
            )
    return count


def _load_workflow_yamls(wf_registry: Any) -> int:
    """Load workflow YAML files from the workflows/ directory."""
    from pathlib import Path

    wf_dir = Path("workflows")
    if not wf_dir.is_dir():
        logger.info("bootstrap.workflows_dir_missing")
        return 0

    count = 0
    for yaml_file in sorted(wf_dir.glob("*.yaml")):
        if yaml_file.name.startswith("_"):
            continue  # skip _schema.yaml
        try:
            wf_registry.register_from_yaml(str(yaml_file))
            count += 1
        except Exception as exc:
            logger.warning(
                "bootstrap.workflow_load_failed",
                file=str(yaml_file),
                error=str(exc),
            )
    return count


async def _init_mcp_servers(tool_registry: Any) -> int:
    """Initialize MCP servers from config and register their tools."""
    settings = get_settings()
    mcp_configs = getattr(settings, "mcp_servers", None)
    if not mcp_configs:
        return 0

    from app.tools.mcp_adapter import (
        MCPServerConfig,
        MCPToolConfig,
        MCPManager,
        get_mcp_manager,
    )

    manager = get_mcp_manager()
    count = 0
    for srv_cfg in mcp_configs:
        if isinstance(srv_cfg, dict):
            tools = [
                MCPToolConfig(
                    name=t.get("name", ""),
                    description=t.get("description", ""),
                )
                for t in srv_cfg.get("tools", [])
            ]
            config = MCPServerConfig(
                name=srv_cfg.get("name", ""),
                url=srv_cfg.get("url", ""),
                transport=srv_cfg.get("transport", "sse"),
                timeout=float(srv_cfg.get("timeout", 30.0)),
                tools=tools,
            )
        else:
            continue

        try:
            await manager.add_server(config)
            logger.info("bootstrap.mcp_server_added", server=config.name)
        except Exception as exc:
            logger.warning(
                "bootstrap.mcp_server_failed",
                server=config.name,
                error=str(exc),
            )

    count = await manager.register_tools(tool_registry)
    return count


async def _shutdown_mcp() -> None:
    """Close all MCP server connections."""
    try:
        from app.tools.mcp_adapter import get_mcp_manager

        manager = get_mcp_manager()
        await manager.close_all()
        logger.info("bootstrap.mcp_closed")
    except Exception as exc:
        logger.warning("bootstrap.mcp_close_failed", error=str(exc))


async def _register_services() -> None:
    from app.infra.circuit_breaker import get_circuit_breaker
    from app.infra.semaphore_manager import get_semaphore_manager
    from app.services.llm.gateway import LLMGateway
    from app.services.llm.router import LLMRouter
    from app.services.context_manager import ContextManager
    from app.tools.registry import ToolRegistry, get_tool_registry
    from app.tools.builtin import register_builtin_tools
    from app.services.skill_registry import SkillRegistry, set_skill_registry

    settings = get_settings()

    cb_settings = settings.circuit_breaker
    cb_names = ["llm_text", "llm_vllm", "multimodal", "embedding"]
    for cb_name in cb_names:
        get_circuit_breaker(
            cb_name,
            failure_threshold=cb_settings.failure_threshold,
            recovery_timeout=float(cb_settings.recovery_timeout),
            half_open_max_calls=cb_settings.half_open_max_calls,
        )

    sem_manager = get_semaphore_manager()

    router = LLMRouter()
    gateway = LLMGateway(
        router=router,
        sem_manager=sem_manager,
        settings=settings,
    )
    container.register(LLMGateway, lambda g=gateway: g, singleton=True)

    redis_client = None
    try:
        from app.infra.redis_client import RedisClient
        redis_client = container.resolve(RedisClient)
    except Exception:
        pass

    context_mgr = ContextManager(
        redis_client=redis_client,
        cache_ttl=settings.context.redis_cache_ttl,
        default_max_tokens=settings.context.default_max_tokens,
        default_strategy=settings.context.default_strategy,
    )
    container.register(ContextManager, lambda cm=context_mgr: cm, singleton=True)

    # --- F10: Tools + Skills ------------------------------------------------
    tool_registry = get_tool_registry()
    builtin_count = register_builtin_tools(tool_registry)
    container.register(ToolRegistry, lambda tr=tool_registry: tr, singleton=True)

    # MCP servers
    mcp_count = await _init_mcp_servers(tool_registry)

    skill_registry = SkillRegistry(tools=tool_registry)
    skills_count = _load_skills(skill_registry)
    set_skill_registry(skill_registry)
    container.register(SkillRegistry, lambda sr=skill_registry: sr, singleton=True)

    # --- F13: Workflow Registry -----------------------------------------------
    from app.workflow.registry import WorkflowRegistry, get_workflow_registry

    wf_registry = get_workflow_registry()
    wf_yaml_count = _load_workflow_yamls(wf_registry)
    container.register(WorkflowRegistry, lambda wr=wf_registry: wr, singleton=True)

    logger.info(
        "bootstrap.services_registered",
        circuit_breakers=cb_names,
        builtin_tools=builtin_count,
        skills=skills_count,
        mcp_tools=mcp_count,
        workflows_yaml=wf_yaml_count,
    )


def get_uptime() -> float:
    if _start_time == 0.0:
        return 0.0
    return round(time.monotonic() - _start_time, 1)


def get_health_status() -> dict[str, Any]:
    from app.core.constants import APP_VERSION

    health_info = container.resolve(dict) if dict in container._factories else {}
    db_status = health_info.get("database", "not_checked")
    redis_status = health_info.get("redis", "not_checked")
    qdrant_status = health_info.get("qdrant", "not_checked")

    if db_status == "error":
        status = "error"
    elif redis_status == "degraded" or qdrant_status == "degraded":
        status = "degraded"
    else:
        status = "ok"

    return {
        "status": status,
        "version": APP_VERSION,
        "uptime": get_uptime(),
        "dependencies": {
            "database": db_status,
            "redis": redis_status,
            "qdrant": qdrant_status,
        },
    }


@asynccontextmanager
async def lifespan(app: Any):
    await startup()
    yield
    await shutdown()