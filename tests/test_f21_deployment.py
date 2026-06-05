"""F21 tests: Docker + deployment + production readiness.

Verification: pytest tests/test_f21_deployment.py
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _create_client() -> TestClient:
    from app.main import app
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Dockerfile validation
# ---------------------------------------------------------------------------


class TestDockerfile:
    """Dockerfile structure and security."""

    def test_dockerfile_exists(self) -> None:
        assert Path("Dockerfile").exists()

    def test_dockerfile_multi_stage(self) -> None:
        content = Path("Dockerfile").read_text(encoding="utf-8")
        assert "AS builder" in content
        assert "AS runtime" in content

    def test_dockerfile_non_root_user(self) -> None:
        content = Path("Dockerfile").read_text(encoding="utf-8")
        assert "useradd" in content or "adduser" in content
        assert "USER " in content

    def test_dockerfile_healthcheck(self) -> None:
        content = Path("Dockerfile").read_text(encoding="utf-8")
        assert "HEALTHCHECK" in content
        assert "/api/v1/health" in content

    def test_dockerfile_exposes_port(self) -> None:
        content = Path("Dockerfile").read_text(encoding="utf-8")
        assert "EXPOSE 6006" in content


# ---------------------------------------------------------------------------
# Docker Compose validation
# ---------------------------------------------------------------------------


class TestDockerCompose:
    """docker-compose.yml structure and health checks."""

    def test_compose_file_exists(self) -> None:
        assert Path("docker-compose.yml").exists()

    def test_compose_has_all_services(self) -> None:
        import yaml
        cfg = yaml.safe_load(Path("docker-compose.yml").read_text(encoding="utf-8"))
        services = cfg.get("services", {})
        assert "postgres" in services
        assert "redis" in services
        assert "qdrant" in services
        assert "app" in services

    def test_compose_app_healthcheck(self) -> None:
        import yaml
        cfg = yaml.safe_load(Path("docker-compose.yml").read_text(encoding="utf-8"))
        app = cfg["services"]["app"]
        assert "healthcheck" in app
        hc = app["healthcheck"]
        assert "/api/v1/health" in str(hc.get("test", []))

    def test_compose_app_depends_on_conditions(self) -> None:
        import yaml
        cfg = yaml.safe_load(Path("docker-compose.yml").read_text(encoding="utf-8"))
        app = cfg["services"]["app"]
        deps = app.get("depends_on", {})
        assert "postgres" in deps
        assert "redis" in deps
        assert "qdrant" in deps

    def test_compose_volumes_declared(self) -> None:
        import yaml
        cfg = yaml.safe_load(Path("docker-compose.yml").read_text(encoding="utf-8"))
        assert "volumes" in cfg
        vols = cfg["volumes"]
        assert "postgres_data" in vols
        assert "redis_data" in vols
        assert "qdrant_data" in vols

    def test_compose_app_volumes_readonly(self) -> None:
        import yaml
        cfg = yaml.safe_load(Path("docker-compose.yml").read_text(encoding="utf-8"))
        app = cfg["services"]["app"]
        vols = app.get("volumes", [])
        for v in vols:
            if ":/app/" in str(v) or ":/run/secrets" in str(v):
                assert str(v).endswith(":ro"), f"Volume {v} should be read-only"


# ---------------------------------------------------------------------------
# .env.example validation
# ---------------------------------------------------------------------------


class TestEnvExample:
    """Environment variable documentation."""

    def test_env_example_exists(self) -> None:
        assert Path(".env.example").exists()

    def test_env_example_has_required_vars(self) -> None:
        content = Path(".env.example").read_text(encoding="utf-8")
        assert "DATABASE_URL=" in content
        assert "REDIS_URL=" in content
        assert "QDRANT_URL=" in content

    def test_env_example_has_auth_var(self) -> None:
        content = Path(".env.example").read_text(encoding="utf-8")
        assert "SECURITY_API_KEY=" in content

    def test_env_example_has_llm_vars(self) -> None:
        content = Path(".env.example").read_text(encoding="utf-8")
        assert "TEXT_MODEL__QWEN_API_KEY=" in content
        assert "TEXT_MODEL__QWEN_API_BASE=" in content


# ---------------------------------------------------------------------------
# Health endpoint (LLM dependency included)
# ---------------------------------------------------------------------------


class TestHealthEndpoint:
    """GET /api/v1/health returns full dependency status including LLM."""

    def test_health_response_structure(self) -> None:
        client = _create_client()
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert "data" in data
        d = data["data"]
        assert "status" in d
        assert "version" in d
        assert "uptime" in d
        assert "dependencies" in d

    def test_health_dependencies_include_llm(self) -> None:
        client = _create_client()
        response = client.get("/api/v1/health")
        data = response.json()
        deps = data["data"]["dependencies"]
        assert "database" in deps
        assert "redis" in deps
        assert "qdrant" in deps
        assert "llm" in deps

    def test_health_llm_has_channels(self) -> None:
        client = _create_client()
        response = client.get("/api/v1/health")
        data = response.json()
        llm = data["data"]["dependencies"]["llm"]
        assert "status" in llm
        assert "channels" in llm

    def test_health_llm_channels_have_status(self) -> None:
        client = _create_client()
        response = client.get("/api/v1/health")
        data = response.json()
        llm = data["data"]["dependencies"]["llm"]
        channels = llm.get("channels", {})
        # Even if no channels are registered, the structure should exist
        for channel_name, channel_data in channels.items():
            assert "status" in channel_data

    def test_health_overall_status_enum(self) -> None:
        client = _create_client()
        response = client.get("/api/v1/health")
        data = response.json()
        status = data["data"]["status"]
        assert status in ("ok", "degraded", "error")


# ---------------------------------------------------------------------------
# Production readiness checklist
# ---------------------------------------------------------------------------


class TestProductionReadiness:
    """Feature list, architecture check, and docs."""

    def test_feature_list_all_passing(self) -> None:
        import json
        fl = json.loads(Path("feature_list.json").read_text(encoding="utf-8"))
        features = fl["features"]
        for f in features:
            if f["id"] == "F21":
                # F21 is the current feature being implemented
                continue
            assert f["state"] == "passing", f"Feature {f['id']} is not passing"

    def test_no_secrets_in_code(self) -> None:
        """Basic check: no obvious hardcoded secrets in Python files."""
        import re
        suspicious = []
        for path in Path("app").rglob("*.py"):
            content = path.read_text(encoding="utf-8")
            # Look for obvious API keys (not empty strings or comments)
            if re.search(r'api_key\s*=\s*"[^"]{10,}"', content):
                if "example" not in content.lower() and "test" not in str(path):
                    suspicious.append(str(path))
        assert not suspicious, f"Possible hardcoded secrets in: {suspicious}"

    def test_gitignore_has_env(self) -> None:
        gitignore = Path(".gitignore")
        if gitignore.exists():
            content = gitignore.read_text(encoding="utf-8")
            assert ".env" in content or ".env.local" in content

    def test_dockerignore_exists_or_env_ignored(self) -> None:
        """.env and secrets should not be copied into Docker images."""
        dockerignore = Path(".dockerignore")
        if dockerignore.exists():
            content = dockerignore.read_text(encoding="utf-8")
            assert ".env" in content
            assert "secrets/" in content or ".git" in content

    def test_architecture_check_script_exists(self) -> None:
        assert Path("scripts/check-architecture.ps1").exists() or Path("scripts/check-architecture.sh").exists()

    def test_docs_updated_for_f21(self) -> None:
        guide = Path("docs/02-engineering/DEPLOYMENT_GUIDE.md")
        content = guide.read_text(encoding="utf-8")
        # Should not have remaining TBD for F21
        assert "[TBD: filled by F21]" not in content
        assert "[filled by F21]" in content
