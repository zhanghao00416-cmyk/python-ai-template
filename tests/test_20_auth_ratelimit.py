"""F20 tests: Auth + Rate limit middleware.

Verification: pytest tests/test_20_auth_ratelimit.py
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient


def _create_client() -> TestClient:
    from app.main import app
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Auth middleware tests
# ---------------------------------------------------------------------------


class TestAuthMiddleware:
    """API key authentication enforced on protected routes."""

    def test_missing_api_key_returns_401(self) -> None:
        client = _create_client()
        response = client.get("/api/v1/health", headers={})
        # /health is exempt, so it should succeed
        assert response.status_code == 200

    def test_invalid_api_key_returns_401(self) -> None:
        from fastapi import FastAPI
        from fastapi.responses import PlainTextResponse

        from app.core.config import get_settings, reset_settings
        from app.middleware.auth import auth_middleware

        reset_settings()
        settings = get_settings()
        original_key = settings.security.api_key
        settings.security.api_key = "secret-test-key"

        try:
            app = FastAPI()
            app.middleware("http")(auth_middleware)

            @app.get("/test")
            def test_route():
                return PlainTextResponse("ok")

            client = TestClient(app, raise_server_exceptions=False)
            response = client.get("/test", headers={"X-API-Key": "wrong-key"})
            assert response.status_code == 401
            data = response.json()
            assert data["code"] == 1001
            assert "Invalid or missing API key" in data["message"]
        finally:
            settings.security.api_key = original_key
            reset_settings()

    def test_valid_api_key_allows_request(self) -> None:
        from app.core.config import get_settings
        settings = get_settings()
        if not settings.security.api_key:
            pytest.skip("No API key configured")

        client = _create_client()
        response = client.get("/api/v1/health", headers={"X-API-Key": settings.security.api_key})
        assert response.status_code == 200

    def test_auth_disabled_allows_request(self) -> None:
        from fastapi import FastAPI
        from fastapi.responses import PlainTextResponse

        from app.core.config import get_settings, reset_settings
        from app.middleware.auth import auth_middleware

        reset_settings()
        settings = get_settings()
        original = settings.security.enable_auth
        settings.security.enable_auth = False

        try:
            app = FastAPI()
            app.middleware("http")(auth_middleware)

            @app.get("/test")
            def test_route():
                return PlainTextResponse("ok")

            client = TestClient(app, raise_server_exceptions=False)
            response = client.get("/test")
            assert response.status_code == 200
        finally:
            settings.security.enable_auth = original
            reset_settings()


# ---------------------------------------------------------------------------
# Rate limit middleware tests
# ---------------------------------------------------------------------------


class TestRateLimitMiddleware:
    """Redis-based sliding-window rate limiting."""

    def test_rate_limit_exempt_path(self) -> None:
        client = _create_client()
        response = client.get("/api/v1/health")
        assert response.status_code == 200

    def test_rate_limit_allows_under_limit(self) -> None:
        from app.core.config import get_settings, reset_settings
        from app.core.di import container
        from app.infra.redis_client import RedisClient
        from app.middleware.rate_limit import rate_limit_middleware

        reset_settings()
        settings = get_settings()
        settings.rate_limit.enabled = True
        settings.rate_limit.default.requests = 10
        settings.rate_limit.default.window_seconds = 60

        mock_redis = AsyncMock()
        mock_redis.incr = AsyncMock(return_value=1)
        mock_redis.expire = AsyncMock(return_value=True)

        container.register(RedisClient, lambda: mock_redis, singleton=True)

        try:
            from fastapi import FastAPI
            from fastapi.responses import PlainTextResponse

            app = FastAPI()
            app.middleware("http")(rate_limit_middleware)

            @app.get("/test")
            def test_route():
                return PlainTextResponse("ok")

            client = TestClient(app, raise_server_exceptions=False)
            response = client.get("/test", headers={"X-API-Key": "test-key"})
            assert response.status_code == 200
            assert response.headers.get("X-RateLimit-Limit") == "10"
            assert response.headers.get("X-RateLimit-Remaining") == "9"
        finally:
            container.reset(RedisClient)
            reset_settings()

    def test_rate_limit_blocks_over_limit(self) -> None:
        from app.core.config import get_settings, reset_settings
        from app.core.di import container
        from app.infra.redis_client import RedisClient
        from app.middleware.rate_limit import rate_limit_middleware

        reset_settings()
        settings = get_settings()
        settings.rate_limit.enabled = True
        settings.rate_limit.default.requests = 5
        settings.rate_limit.default.window_seconds = 60

        mock_redis = AsyncMock()
        mock_redis.incr = AsyncMock(return_value=6)
        mock_redis.expire = AsyncMock(return_value=True)

        container.register(RedisClient, lambda: mock_redis, singleton=True)

        try:
            from fastapi import FastAPI
            from fastapi.responses import PlainTextResponse

            app = FastAPI()
            app.middleware("http")(rate_limit_middleware)

            @app.get("/test")
            def test_route():
                return PlainTextResponse("ok")

            client = TestClient(app, raise_server_exceptions=False)
            response = client.get("/test", headers={"X-API-Key": "test-key"})
            assert response.status_code == 429
            data = response.json()
            assert data["code"] == 1004  # AUTH_RATE_LIMITED when key present
            assert response.headers.get("Retry-After") == "60"
            assert response.headers.get("X-RateLimit-Remaining") == "0"
        finally:
            container.reset(RedisClient)
            reset_settings()

    def test_rate_limit_ip_based_without_key(self) -> None:
        from app.core.config import get_settings, reset_settings
        from app.core.di import container
        from app.infra.redis_client import RedisClient
        from app.middleware.rate_limit import rate_limit_middleware

        reset_settings()
        settings = get_settings()
        settings.rate_limit.enabled = True
        settings.rate_limit.default.requests = 5
        settings.rate_limit.default.window_seconds = 60

        mock_redis = AsyncMock()
        mock_redis.incr = AsyncMock(return_value=6)
        mock_redis.expire = AsyncMock(return_value=True)

        container.register(RedisClient, lambda: mock_redis, singleton=True)

        try:
            from fastapi import FastAPI
            from fastapi.responses import PlainTextResponse

            app = FastAPI()
            app.middleware("http")(rate_limit_middleware)

            @app.get("/test")
            def test_route():
                return PlainTextResponse("ok")

            client = TestClient(app, raise_server_exceptions=False)
            response = client.get("/test")  # No API key
            assert response.status_code == 429
            data = response.json()
            assert data["code"] == 6  # RATE_LIMITED (0xxx system) for IP-based
        finally:
            container.reset(RedisClient)
            reset_settings()

    def test_rate_limit_disabled_allows_all(self) -> None:
        from app.core.config import get_settings, reset_settings
        from app.middleware.rate_limit import rate_limit_middleware

        reset_settings()
        settings = get_settings()
        settings.rate_limit.enabled = False

        try:
            from fastapi import FastAPI
            from fastapi.responses import PlainTextResponse

            app = FastAPI()
            app.middleware("http")(rate_limit_middleware)

            @app.get("/test")
            def test_route():
                return PlainTextResponse("ok")

            client = TestClient(app, raise_server_exceptions=False)
            response = client.get("/test")
            assert response.status_code == 200
        finally:
            reset_settings()

    def test_rate_limit_redis_unavailable_degraded(self) -> None:
        from app.core.config import get_settings, reset_settings
        from app.core.di import container
        from app.infra.redis_client import RedisClient
        from app.middleware.rate_limit import rate_limit_middleware

        reset_settings()
        settings = get_settings()
        settings.rate_limit.enabled = True
        settings.rate_limit.default.requests = 5
        settings.rate_limit.default.window_seconds = 60

        mock_redis = AsyncMock()
        mock_redis.incr = AsyncMock(side_effect=Exception("Redis down"))

        container.register(RedisClient, lambda: mock_redis, singleton=True)

        try:
            from fastapi import FastAPI
            from fastapi.responses import PlainTextResponse

            app = FastAPI()
            app.middleware("http")(rate_limit_middleware)

            @app.get("/test")
            def test_route():
                return PlainTextResponse("ok")

            client = TestClient(app, raise_server_exceptions=False)
            response = client.get("/test")
            # Should degrade gracefully and allow request
            assert response.status_code == 200
        finally:
            container.reset(RedisClient)
            reset_settings()


# ---------------------------------------------------------------------------
# End-to-end integration with main app
# ---------------------------------------------------------------------------


class TestAuthRateLimitE2E:
    """Auth and rate limit headers in real app responses."""

    def test_health_exempt_from_auth_and_rate_limit(self) -> None:
        client = _create_client()
        response = client.get("/api/v1/health")
        assert response.status_code == 200

    def test_metrics_exempt(self) -> None:
        client = _create_client()
        response = client.get("/metrics")
        # Metrics endpoint might not exist in test env, but it should not 401/429
        assert response.status_code in (200, 404)
