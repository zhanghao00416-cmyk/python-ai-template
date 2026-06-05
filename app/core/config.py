from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
_CONFIG_DIR = ROOT_DIR / "configs"
_ENV_FILE = ROOT_DIR / ".env"
_SECRETS_DIR = Path("/run/secrets")

# Flat env keys and legacy-style keys → dotted yaml path
_ENV_TO_YAML: dict[str, str] = {
    "DATABASE_URL": "database.url",
    "REDIS_URL": "redis.url",
    "QDRANT_URL": "qdrant.url",
    "QDRANT__URL": "qdrant.url",
    "QWEN_API_KEY": "text_model.qwen_api_key",
    "TEXT_MODEL__QWEN_API_KEY": "text_model.qwen_api_key",
    "TEXT_MODEL__QWEN_API_BASE": "text_model.qwen_api_base",
    "TEXT_MODEL__QWEN_MODEL_NAME": "text_model.qwen_model_name",
    "TEXT_MODEL__TEXT_MODEL_PROVIDER": "text_model.text_model_provider",
    "TEXT_MODEL__TEXT_VLLM_BASE_URL": "text_model.text_vllm_base_url",
    "TEXT_MODEL__TEXT_VLLM_MODEL": "text_model.text_vllm_model",
    "VLLM_BASE_URL": "text_model.text_vllm_base_url",
    "SECURITY_API_KEY": "security.api_key",
    "SECURITY__API_KEY": "security.api_key",
    "SECURITY__JWT_SECRET": "security.jwt_secret",
    "JWT_SECRET": "security.jwt_secret",
    "SERVER_HOST": "server.host",
    "SERVER_PORT": "server.port",
    "SERVER_DEBUG": "server.debug",
    "LOGGING_LEVEL": "logging.level",
    "LOG_LEVEL": "logging.level",
    "SSE_HEARTBEAT_INTERVAL": "sse.heartbeat_interval",
    "PROMPT_CONFIG__PROMPTS_DIR": "prompt_config.prompts_dir",
}


def _read_secret(name: str) -> str:
    """Docker Secrets: /run/secrets/<name> file; empty if missing."""
    path = _SECRETS_DIR / name
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()
    return ""


def _load_env_file() -> None:
    """Load repo-root .env into os.environ; existing env vars win (compose/K8s)."""
    if not _ENV_FILE.is_file():
        return
    for raw in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


def _load_yaml(path: Path) -> dict[str, Any]:
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def _deep_merge(base: dict, override: dict) -> dict:
    merged = base.copy()
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


class ServerSettings(BaseSettings):
    host: str = "0.0.0.0"
    port: int = 6006
    debug: bool = False
    debug_sse_output: bool = False

    model_config = {"env_prefix": "SERVER_"}

    @field_validator("port", mode="before")
    @classmethod
    def _coerce_port(cls, value: object) -> object:
        if isinstance(value, str) and value.isdigit():
            return int(value)
        return value

    @field_validator("debug", "debug_sse_output", mode="before")
    @classmethod
    def _coerce_bool(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "yes", "on")
        return value


class DatabaseSettings(BaseSettings):
    url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/ai_platform"
    pool_size: int = 10
    max_overflow: int = 20

    model_config = {"env_prefix": "DATABASE_"}


class RedisSettings(BaseSettings):
    url: str = "redis://localhost:6379/0"
    default_ttl: int = 3600

    model_config = {"env_prefix": "REDIS_"}


class QdrantSettings(BaseSettings):
    url: str = "http://localhost:6333"
    timeout: int = 30
    sparse_vector_name: str = "bm25"

    model_config = {"env_prefix": "QDRANT_"}


class KnowledgeCollectionSettings(BaseSettings):
    name: str = "general"
    description: str = ""
    vector_dim: int = 1024
    distance: str = "Cosine"
    sparse_vector: bool = True
    default_chunk_size: int = 500
    default_chunk_overlap: int = 50

    model_config = {"env_prefix": "KNOWLEDGE_COLLECTION_"}


class RetrievalSettings(BaseSettings):
    default_top_k: int = 3
    default_score_threshold: float = 0.5
    enable_hybrid: bool = True
    hybrid_alpha: float = 0.7
    enable_rerank: bool = False

    model_config = {"env_prefix": "RETRIEVAL_"}


class KnowledgeSettings(BaseSettings):
    collections: list[dict[str, Any]] = []
    retrieval: RetrievalSettings = RetrievalSettings()

    model_config = {"env_prefix": "KNOWLEDGE_"}


class SecuritySettings(BaseSettings):
    enable_auth: bool = True
    api_key: str = ""
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    max_body_size: int = 10485760

    model_config = {"env_prefix": "SECURITY_"}


class RateLimitEndpointSettings(BaseSettings):
    requests: int = 100
    window_seconds: int = 60


class RateLimitSettings(BaseSettings):
    enabled: bool = True
    default: RateLimitEndpointSettings = RateLimitEndpointSettings()
    endpoints: dict[str, RateLimitEndpointSettings] = {}
    exempt_paths: list[str] = ["/api/v1/health", "/metrics"]

    model_config = {"env_prefix": "RATE_LIMIT_"}


class TextModelSettings(BaseSettings):
    text_model_provider: str = "qwen_cloud"
    qwen_api_base: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    qwen_api_key: str = ""
    qwen_model_name: str = "qwen-plus"
    text_vllm_base_url: str = ""
    text_vllm_model: str = "Qwen3.5-9B"
    text_timeout: int = 120

    model_config = {"env_prefix": "TEXT_MODEL_", "extra": "ignore"}


class LoggingSettings(BaseSettings):
    level: str = "INFO"
    format: str = "json"
    otel_enabled: bool = False
    otel_endpoint: str = "http://localhost:4317"

    model_config = {"env_prefix": "LOGGING_"}


class SSESettings(BaseSettings):
    heartbeat_interval: int = 15

    model_config = {"env_prefix": "SSE_"}


class ConcurrencySettings(BaseSettings):
    llm_semaphore_size: int = 20
    multimodal_semaphore_size: int = 10
    embedding_semaphore_size: int = 20
    semaphore_acquire_timeout: int = 120

    model_config = {"env_prefix": "CONCURRENCY_"}


class CircuitBreakerSettings(BaseSettings):
    failure_threshold: int = 5
    recovery_timeout: int = 30
    half_open_max_calls: int = 1

    model_config = {"env_prefix": "CIRCUIT_BREAKER_"}


class PromptConfigSettings(BaseSettings):
    prompts_dir: str = "./prompts"
    prompts_default_dir: str = "./prompts/prompts_default"

    model_config = {"env_prefix": "PROMPT_CONFIG_"}


class JsonRepairSettings(BaseSettings):
    enabled: bool = True

    model_config = {"env_prefix": "JSON_REPAIR_"}


class TaskQueueSettings(BaseSettings):
    redis_queue_name: str = "arq:tasks"
    max_retries: int = 3
    retry_delay: int = 60

    model_config = {"env_prefix": "TASK_QUEUE_"}


class ContextSettings(BaseSettings):
    redis_cache_ttl: int = 3600
    default_max_tokens: int = 4096
    default_strategy: str = "recent_priority"

    model_config = {"env_prefix": "CONTEXT_"}


class WorkflowSettings(BaseSettings):
    max_concurrent_nodes: int = 5

    model_config = {"env_prefix": "WORKFLOW_"}


class Settings(BaseSettings):
    server: ServerSettings = ServerSettings()
    database: DatabaseSettings = DatabaseSettings()
    redis: RedisSettings = RedisSettings()
    qdrant: QdrantSettings = QdrantSettings()
    knowledge: KnowledgeSettings = KnowledgeSettings()
    security: SecuritySettings = SecuritySettings()
    text_model: TextModelSettings = TextModelSettings()
    logging: LoggingSettings = LoggingSettings()
    sse: SSESettings = SSESettings()
    concurrency: ConcurrencySettings = ConcurrencySettings()
    circuit_breaker: CircuitBreakerSettings = CircuitBreakerSettings()
    prompt_config: PromptConfigSettings = PromptConfigSettings()
    json_repair: JsonRepairSettings = JsonRepairSettings()
    task_queue: TaskQueueSettings = TaskQueueSettings()
    context: ContextSettings = ContextSettings()
    workflow: WorkflowSettings = WorkflowSettings()
    rate_limit: RateLimitSettings = RateLimitSettings()
    embedding: dict[str, Any] = Field(default_factory=dict)
    mcp_servers: list[dict[str, Any]] = []
    intent: dict[str, Any] = Field(default_factory=dict)

    model_config = {"env_prefix": ""}

    @classmethod
    def from_yaml(cls) -> "Settings":
        default_cfg = _load_yaml(_CONFIG_DIR / "default.yaml")
        override_cfg = _load_yaml(_CONFIG_DIR / "override.yaml")
        merged = _deep_merge(default_cfg, override_cfg)

        _load_env_file()
        for yaml_path, value in _collect_env_overrides().items():
            _set_nested(merged, yaml_path, value)
        _apply_secrets_to_merged(merged)

        settings = cls()
        _apply_yaml_to_settings(settings, merged)
        # Apply list-type config sections (e.g. mcp_servers)
        if "mcp_servers" in merged and isinstance(merged["mcp_servers"], list):
            settings.mcp_servers = merged["mcp_servers"]
        return settings


def _collect_env_overrides() -> dict[str, str]:
    overrides: dict[str, str] = {}
    for env_var, yaml_path in _ENV_TO_YAML.items():
        value = os.environ.get(env_var)
        if value is not None and value != "":
            overrides[yaml_path] = value
    return overrides


def _apply_secrets_to_merged(merged: dict[str, Any]) -> None:
    """Highest priority: /run/secrets files."""
    secret_map: list[tuple[str, str, str]] = [
        ("qwen_api_key", "text_model", "qwen_api_key"),
        ("api_key", "security", "api_key"),
        ("jwt_secret", "security", "jwt_secret"),
    ]
    for filename, section, field in secret_map:
        secret_value = _read_secret(filename)
        if secret_value:
            merged.setdefault(section, {})
            if isinstance(merged[section], dict):
                merged[section][field] = secret_value


def _set_nested(d: dict, path: str, value: Any) -> None:
    keys = path.split(".")
    for key in keys[:-1]:
        d = d.setdefault(key, {})
    d[keys[-1]] = value


def _coerce_setting_value(section: BaseSettings, key: str, value: Any) -> Any:
    """Coerce env/.env string values to match section field types."""
    field = type(section).model_fields.get(key)
    if field is None:
        return value
    ann = field.annotation
    if ann is int:
        if isinstance(value, str) and value.lstrip("-").isdigit():
            return int(value)
        if isinstance(value, str):
            try:
                return int(value)
            except ValueError:
                return value
    if ann is bool and isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return value


def _apply_yaml_to_settings(settings: Settings, cfg: dict[str, Any]) -> None:
    for section_name, section_data in cfg.items():
        if not isinstance(section_data, dict):
            continue
        section = getattr(settings, section_name, None)
        if section is None:
            continue
        # Support free-form dict sections (e.g. embedding) directly.
        if isinstance(section, dict):
            merged = dict(section)
            for key, value in section_data.items():
                merged[key] = value
            setattr(settings, section_name, merged)
            continue
        payload = section.model_dump()
        for key, value in section_data.items():
            if key in payload:
                payload[key] = _coerce_setting_value(section, key, value)
        try:
            setattr(settings, section_name, type(section)(**payload))
        except (ValidationError, TypeError):
            pass


try:
    from pydantic import ValidationError
except ImportError:
    ValidationError = TypeError

_settings_instance: Settings | None = None


def get_settings() -> Settings:
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = Settings.from_yaml()
    return _settings_instance


def reset_settings() -> None:
    global _settings_instance
    _settings_instance = None
