from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def _create_client() -> TestClient:
    from app.main import app
    return TestClient(app, raise_server_exceptions=False)


class TestSkeleton:
    def test_app_importable(self) -> None:
        from app.main import app
        assert app is not None

    def test_health_endpoint_returns_200(self) -> None:
        client = _create_client()
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert data["message"] == "ok"
        assert "data" in data
        assert "version" in data["data"]
        assert "status" in data["data"]
        assert "dependencies" in data["data"]

    def test_health_response_has_request_trace_ids(self) -> None:
        client = _create_client()
        response = client.get(
            "/api/v1/health",
            headers={"X-Trace-Id": "trace-123", "X-Request-Id": "req-456"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["request_id"] != "" or data["trace_id"] == "trace-123"

    def test_config_loads_from_yaml(self) -> None:
        from app.core.config import get_settings
        settings = get_settings()
        assert settings.server.port == 6006
        assert settings.server.host == "0.0.0.0"
        assert settings.sse.heartbeat_interval == 15

    def test_secret_overrides_env_and_yaml(self, tmp_path, monkeypatch) -> None:
        from app.core import config as cfg

        cfg.reset_settings()
        env_path = tmp_path / ".env"
        env_path.write_text("SECURITY_API_KEY=from-dotenv\nTEXT_MODEL__QWEN_API_KEY=from-dotenv-qwen\n", encoding="utf-8")
        secrets_dir = tmp_path / "secrets"
        secrets_dir.mkdir()
        (secrets_dir / "api_key").write_text("from-secret-file", encoding="utf-8")
        (secrets_dir / "qwen_api_key").write_text("qwen-from-secret", encoding="utf-8")

        monkeypatch.setattr(cfg, "ROOT_DIR", tmp_path)
        monkeypatch.setattr(cfg, "_ENV_FILE", env_path)
        monkeypatch.setattr(cfg, "_SECRETS_DIR", secrets_dir)
        monkeypatch.setattr(cfg, "_CONFIG_DIR", tmp_path / "configs")
        (tmp_path / "configs").mkdir()
        (tmp_path / "configs" / "default.yaml").write_text(
            "server:\n  port: 6006\nsecurity:\n  api_key: ''\ntext_model:\n  qwen_api_key: ''\n",
            encoding="utf-8",
        )

        settings = cfg.get_settings()
        assert settings.security.api_key == "from-secret-file"
        assert settings.text_model.qwen_api_key == "qwen-from-secret"
        cfg.reset_settings()

    def test_di_container_register_resolve(self) -> None:
        from app.core.di import DIContainer

        c = DIContainer()
        c.register(int, lambda: 42, singleton=True)
        assert c.resolve(int) == 42
        assert c.resolve(int) == 42

    def test_di_container_transient(self) -> None:
        from app.core.di import DIContainer

        c = DIContainer()
        counter = {"n": 0}

        def factory():
            counter["n"] += 1
            return counter["n"]

        c.register(int, factory, singleton=False)
        assert c.resolve(int) == 1
        assert c.resolve(int) == 2

    def test_di_container_override_and_reset(self) -> None:
        from app.core.di import DIContainer

        c = DIContainer()
        c.register(str, lambda: "original", singleton=True)
        assert c.resolve(str) == "original"
        c.override(str, lambda: "mock")
        assert c.resolve(str) == "mock"
        c.reset(str)
        assert c.resolve(str) == "original"

    def test_di_container_cleanup(self) -> None:
        from app.core.di import DIContainer

        c = DIContainer()
        c.register(list, lambda: [1, 2, 3], singleton=True)
        result = c.resolve(list)
        assert result == [1, 2, 3]
        c.cleanup()
        assert c._instances == {}

    def test_error_hierarchy(self) -> None:
        from app.core.errors import AppError, SystemError, ErrorCode

        err = SystemError(ErrorCode.INTERNAL_ERROR, "test error")
        assert isinstance(err, AppError)
        assert err.code == 1
        assert err.message == "test error"

    def test_response_helpers(self) -> None:
        from app.core.response import ok_response, error_response, validation_error_response
        from app.core.errors import SystemError, ErrorCode

        ok = ok_response(data={"key": "val"}, request_id="r1", trace_id="t1")
        assert ok["code"] == 0
        assert ok["data"]["key"] == "val"

        err = error_response(SystemError(ErrorCode.CONFIG_ERROR, "bad config"), request_id="r2", trace_id="t2")
        assert err["code"] == 2

        ve = validation_error_response("missing field", request_id="r3", trace_id="t3")
        assert ve["code"] == 5

    def test_context_vars(self) -> None:
        from app.core.context import (
            trace_id_var, request_id_var, user_id_var, session_id_var,
        )

        trace_id_var.set("t1")
        request_id_var.set("r1")
        assert trace_id_var.get() == "t1"
        assert request_id_var.get() == "r1"
        trace_id_var.set("")
        request_id_var.set("")

    def test_constants(self) -> None:
        from app.core.constants import APP_VERSION, API_PREFIX
        assert APP_VERSION == "0.1.0"
        assert API_PREFIX == "/api/v1"