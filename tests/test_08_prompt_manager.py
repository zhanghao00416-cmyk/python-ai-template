from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.errors import ErrorCode, TaskError, make_error
from app.domain.prompt.repo import PromptTemplateRepo, PromptTemplateVersionRepo, extract_template_variables
from app.domain.prompt.service import PromptDomainService
from app.services.prompt_manager import PromptManager, extract_variables


# ===========================================================================
# TestPromptManager (core service)
# ===========================================================================

class TestPromptManagerInit:
    def test_default_dirs(self):
        pm = PromptManager()
        assert pm.prompts_dir == Path("./prompts")
        assert pm.prompts_default_dir == Path("./prompts/prompts_default")

    def test_custom_dirs(self, tmp_path):
        prompts_dir = tmp_path / "prompts"
        default_dir = tmp_path / "defaults"
        prompts_dir.mkdir()
        default_dir.mkdir()
        pm = PromptManager(prompts_dir=str(prompts_dir), prompts_default_dir=str(default_dir))
        assert pm.prompts_dir == prompts_dir
        assert pm.prompts_default_dir == default_dir


class TestPromptManagerPreload:
    def test_preload_loads_md_files(self, tmp_path):
        prompts_dir = tmp_path / "prompts"
        agents_dir = prompts_dir / "agents"
        skills_dir = prompts_dir / "skills"
        agents_dir.mkdir(parents=True)
        skills_dir.mkdir()

        (agents_dir / "researcher.md").write_text("You are a researcher. {{query}}", encoding="utf-8")
        (skills_dir / "rag_answer.md").write_text("Answer: {{context}} {{query}}", encoding="utf-8")

        pm = PromptManager(prompts_dir=str(prompts_dir), prompts_default_dir=str(tmp_path / "defaults"))
        count = pm.preload()

        assert count == 2

    def test_preload_loads_flat_files(self, tmp_path):
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "test.md").write_text("Hello {{name}}", encoding="utf-8")
        (prompts_dir / "greet.md").write_text("Greetings", encoding="utf-8")

        pm = PromptManager(prompts_dir=str(prompts_dir), prompts_default_dir=str(tmp_path / "defaults"))
        count = pm.preload()

        assert count == 2
        assert pm.get_cached("test") is not None
        assert pm.get_cached("greet") is not None

    def test_preload_empty_dir(self, tmp_path):
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        pm = PromptManager(prompts_dir=str(prompts_dir), prompts_default_dir=str(tmp_path / "defaults"))
        count = pm.preload()
        assert count == 0

    def test_get_cached_returns_content(self, tmp_path):
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "test.md").write_text("Hello {{name}}", encoding="utf-8")

        pm = PromptManager(prompts_dir=str(prompts_dir), prompts_default_dir=str(tmp_path / "defaults"))
        pm.preload()

        content = pm.get_cached("test")
        assert content == "Hello {{name}}"

    def test_get_cached_not_found(self, tmp_path):
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        pm = PromptManager(prompts_dir=str(prompts_dir), prompts_default_dir=str(tmp_path / "defaults"))
        pm.preload()
        assert pm.get_cached("nonexistent") is None

    def test_get_cached_by_leaf_name(self, tmp_path):
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "researcher.md").write_text("Research content", encoding="utf-8")

        pm = PromptManager(prompts_dir=str(prompts_dir), prompts_default_dir=str(tmp_path / "defaults"))
        pm.preload()

        content = pm.get_cached("researcher")
        assert content == "Research content"


class TestPromptManagerSeedDefaults:
    def test_seed_copies_missing_files(self, tmp_path):
        default_dir = tmp_path / "defaults"
        default_dir.mkdir()
        (default_dir / "test.md").write_text("Default content", encoding="utf-8")

        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()

        pm = PromptManager(prompts_dir=str(prompts_dir), prompts_default_dir=str(default_dir))
        results = pm.seed_defaults()

        assert results.get("test") == "seeded"
        assert (prompts_dir / "test.md").read_text(encoding="utf-8") == "Default content"

    def test_seed_skips_existing_files(self, tmp_path):
        default_dir = tmp_path / "defaults"
        default_dir.mkdir()
        (default_dir / "test.md").write_text("Default content", encoding="utf-8")

        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "test.md").write_text("Custom content", encoding="utf-8")

        pm = PromptManager(prompts_dir=str(prompts_dir), prompts_default_dir=str(default_dir))
        results = pm.seed_defaults()

        assert results.get("test") == "already_exists"
        assert (prompts_dir / "test.md").read_text(encoding="utf-8") == "Custom content"

    def test_seed_no_default_dir(self, tmp_path):
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        pm = PromptManager(prompts_dir=str(prompts_dir), prompts_default_dir=str(tmp_path / "nonexistent"))
        results = pm.seed_defaults()
        assert len(results) == 0


class TestPromptManagerRender:
    def test_render_replaces_variables(self, tmp_path):
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "greet.md").write_text("Hello {{name}}, welcome to {{place}}!", encoding="utf-8")

        pm = PromptManager(prompts_dir=str(prompts_dir), prompts_default_dir=str(tmp_path / "defaults"))
        pm.preload()

        result = pm.render("greet", {"name": "Alice", "place": "Wonderland"})
        assert result == "Hello Alice, welcome to Wonderland!"

    def test_render_missing_template_raises(self, tmp_path):
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        pm = PromptManager(prompts_dir=str(prompts_dir), prompts_default_dir=str(tmp_path / "defaults"))
        pm.preload()

        with pytest.raises(KeyError, match="not found"):
            pm.render("missing", {"key": "value"})

    def test_render_no_variables(self, tmp_path):
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "static.md").write_text("No variables here.", encoding="utf-8")

        pm = PromptManager(prompts_dir=str(prompts_dir), prompts_default_dir=str(tmp_path / "defaults"))
        pm.preload()

        result = pm.render("static")
        assert result == "No variables here."


class TestPromptManagerValidateName:
    def test_valid_simple_name(self):
        pm = PromptManager()
        assert pm.validate_name("rag_answer") is True
        assert pm.validate_name("agents/researcher") is True

    def test_rejects_path_traversal(self):
        pm = PromptManager()
        assert pm.validate_name("../../etc/passwd") is False

    def test_rejects_empty_name(self):
        pm = PromptManager()
        assert pm.validate_name("") is False

    def test_rejects_special_chars(self):
        pm = PromptManager()
        assert pm.validate_name('test<prompt>') is False


class TestPromptManagerLoadFromFile:
    def test_load_from_cache_path(self, tmp_path):
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "test.md").write_text("Cache content", encoding="utf-8")

        pm = PromptManager(prompts_dir=str(prompts_dir), prompts_default_dir=str(tmp_path / "defaults"))
        pm.preload()

        content = pm.load_from_file("test")
        assert content == "Cache content"

    def test_load_from_default_dir(self, tmp_path):
        default_dir = tmp_path / "defaults"
        default_dir.mkdir()
        (default_dir / "baseline.md").write_text("Baseline content", encoding="utf-8")

        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()

        pm = PromptManager(prompts_dir=str(prompts_dir), prompts_default_dir=str(default_dir))
        result = pm.load_from_file("baseline")
        assert result == "Baseline content"


class TestPromptManagerUpdateCache:
    def test_update_cache(self, tmp_path):
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "test.md").write_text("Original", encoding="utf-8")

        pm = PromptManager(prompts_dir=str(prompts_dir), prompts_default_dir=str(tmp_path / "defaults"))
        pm.preload()
        pm.update_cache("test", "Updated", "")

        assert pm.get_cached("test") == "Updated"

    def test_list_cached(self, tmp_path):
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "a.md").write_text("A", encoding="utf-8")
        (prompts_dir / "b.md").write_text("B", encoding="utf-8")

        pm = PromptManager(prompts_dir=str(prompts_dir), prompts_default_dir=str(tmp_path / "defaults"))
        pm.preload()

        cached = pm.list_cached()
        assert len(cached) == 2


# ===========================================================================
# TestExtractVariables
# ===========================================================================

class TestExtractVariables:
    def test_extract_single(self):
        result = extract_template_variables("Hello {{name}}")
        assert result == ["name"]

    def test_extract_multiple(self):
        result = extract_template_variables("{{query}} and {{context}} and {{query}}")
        assert result == ["query", "context"]

    def test_extract_none(self):
        result = extract_template_variables("No variables here")
        assert result == []

    def test_extract_preserves_order(self):
        result = extract_template_variables("{{a}} {{b}} {{a}} {{c}}")
        assert result == ["a", "b", "c"]

    def test_module_level_extract_variables(self):
        result = extract_variables("{{x}} and {{y}}")
        assert result == ["x", "y"]


# ===========================================================================
# TestPromptDomainService
# ===========================================================================

def _make_template_model(name="test", directory="skills", content="Hello {{name}}",
                         version=1, **kwargs):
    model = MagicMock()
    model.id = uuid4()
    model.name = name
    model.directory = directory
    model.description = kwargs.get("description", "Test prompt")
    model.content = content
    model.variables = kwargs.get("variables", ["name"])
    model.version = version
    model.baseline_content = kwargs.get("baseline_content", content)
    model.baseline_version = kwargs.get("baseline_version", 1)
    model.created_at = datetime.now(timezone.utc)
    model.updated_at = datetime.now(timezone.utc)
    return model


def _make_service(repo=None, version_repo=None, pm=None):
    if repo is None:
        repo = AsyncMock(spec=PromptTemplateRepo)
    if version_repo is None:
        version_repo = AsyncMock(spec=PromptTemplateVersionRepo)
    if pm is None:
        pm = MagicMock(spec=PromptManager)
    return PromptDomainService(
        template_repo=repo,
        version_repo=version_repo,
        prompt_manager=pm,
    ), repo, version_repo, pm


class TestDomainServiceGetTemplate:
    @pytest.mark.asyncio
    async def test_get_template_found(self):
        service, repo, vrepo, pm = _make_service()
        template = _make_template_model(name="rag_answer", content="Answer: {{query}}")
        repo.get_by_name.return_value = template

        result = await service.get_template("rag_answer")
        assert result.name == "rag_answer"
        assert result.content == "Answer: {{query}}"

    @pytest.mark.asyncio
    async def test_get_template_not_found(self):
        service, repo, vrepo, pm = _make_service()
        repo.get_by_name.return_value = None

        with pytest.raises(TaskError) as exc_info:
            await service.get_template("nonexistent")
        assert exc_info.value.code == ErrorCode.PROMPT_NOT_FOUND


class TestDomainServiceListTemplates:
    @pytest.mark.asyncio
    async def test_list_templates(self):
        service, repo, vrepo, pm = _make_service()
        items = [_make_template_model(name="a"), _make_template_model(name="b")]
        repo.list_templates.return_value = (items, 2)

        results, total = await service.list_templates()
        assert total == 2
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_list_templates_with_filter(self):
        service, repo, vrepo, pm = _make_service()
        items = [_make_template_model(name="rag", directory="skills")]
        repo.list_templates.return_value = (items, 1)

        results, total = await service.list_templates(directory="skills")
        assert total == 1


class TestDomainServiceUpdateTemplate:
    @pytest.mark.asyncio
    async def test_update_with_content(self):
        service, repo, vrepo, pm = _make_service()
        template = _make_template_model(name="test", version=1)
        repo.get_by_name.return_value = template
        updated = _make_template_model(name="test", version=2, content="New content")
        repo.update_template.return_value = updated
        vrepo.create_version.return_value = MagicMock()

        result = await service.update_template("test", content="New content")
        assert result.version == 2
        assert result.previous_version == 1

    @pytest.mark.asyncio
    async def test_update_with_rollback_version(self):
        service, repo, vrepo, pm = _make_service()
        template = _make_template_model(name="test", version=3)
        repo.get_by_name.return_value = template
        updated = _make_template_model(name="test", version=4, content="Old content")
        repo.update_template.return_value = updated
        vrepo.get_version.return_value = MagicMock(content="Old content", version=1)
        vrepo.create_version.return_value = MagicMock()

        result = await service.update_template("test", rollback_version=1)
        assert result.version == 4

    @pytest.mark.asyncio
    async def test_update_mutually_exclusive_validation(self):
        service, repo, vrepo, pm = _make_service()

        with pytest.raises(TaskError) as exc_info:
            await service.update_template("test", content="x", rollback_version=1)
        assert exc_info.value.code == ErrorCode.VALIDATION_ERROR

    @pytest.mark.asyncio
    async def test_update_neither_content_nor_rollback(self):
        service, repo, vrepo, pm = _make_service()

        with pytest.raises(TaskError) as exc_info:
            await service.update_template("test")
        assert exc_info.value.code == ErrorCode.VALIDATION_ERROR

    @pytest.mark.asyncio
    async def test_update_template_not_found(self):
        service, repo, vrepo, pm = _make_service()
        repo.get_by_name.return_value = None

        with pytest.raises(TaskError) as exc_info:
            await service.update_template("nonexistent", content="x")
        assert exc_info.value.code == ErrorCode.PROMPT_NOT_FOUND


class TestDomainServiceResetTemplate:
    @pytest.mark.asyncio
    async def test_reset_to_baseline(self):
        service, repo, vrepo, pm = _make_service()
        template = _make_template_model(name="rag_answer", version=5, baseline_content="Original", baseline_version=1)
        repo.get_by_name.return_value = template
        updated = _make_template_model(name="rag_answer", version=6, content="Original")
        repo.update_template.return_value = updated
        vrepo.create_version.return_value = MagicMock()
        pm.load_from_file.return_value = "Original from file"
        pm.get_cached.return_value = "Original from file"

        result = await service.reset_template("rag_answer")
        assert result.version == 6
        assert result.reset_from_version == 5
        assert result.baseline_source is not None

    @pytest.mark.asyncio
    async def test_reset_template_not_found(self):
        service, repo, vrepo, pm = _make_service()
        repo.get_by_name.return_value = None

        with pytest.raises(TaskError) as exc_info:
            await service.reset_template("nonexistent")
        assert exc_info.value.code == ErrorCode.PROMPT_NOT_FOUND


class TestDomainServiceGetVersions:
    @pytest.mark.asyncio
    async def test_get_versions(self):
        service, repo, vrepo, pm = _make_service()
        template = _make_template_model(name="test", version=3)
        repo.get_by_name.return_value = template

        v1 = MagicMock()
        v1.version = 3
        v1.content = "Version 3 content here"
        v1.description = "Latest"
        v1.updated_by = "system"
        v1.created_at = datetime.now(timezone.utc)

        v2 = MagicMock()
        v2.version = 2
        v2.content = "Version 2"
        v2.description = "Previous"
        v2.updated_by = "user1"
        v2.created_at = datetime.now(timezone.utc)

        vrepo.get_versions_by_template_id.return_value = ([v1, v2], 2)

        result = await service.get_versions("test")
        assert result.name == "test"
        assert result.current_version == 3
        assert len(result.versions) == 2

    @pytest.mark.asyncio
    async def test_get_versions_template_not_found(self):
        service, repo, vrepo, pm = _make_service()
        repo.get_by_name.return_value = None

        with pytest.raises(TaskError) as exc_info:
            await service.get_versions("nonexistent")
        assert exc_info.value.code == ErrorCode.PROMPT_NOT_FOUND


class TestDomainServiceRender:
    def test_render_with_variables(self):
        pm_mock = MagicMock(spec=PromptManager)
        pm_mock.get_cached.return_value = "Hello {{name}}, {{query}}"
        pm_mock.load_from_file.return_value = "Hello {{name}}, {{query}}"

        service, repo, vrepo, _ = _make_service(pm=pm_mock)
        result = service.render("greet", {"name": "Alice", "query": "how are you?"})
        assert result.name == "greet"
        assert result.content == "Hello Alice, how are you?"
        assert result.variables == {"name": "Alice", "query": "how are you?"}

    def test_render_template_not_in_cache(self):
        pm_mock = MagicMock(spec=PromptManager)
        pm_mock.get_cached.return_value = None
        pm_mock.load_from_file.return_value = None

        service, repo, vrepo, _ = _make_service(pm=pm_mock)
        with pytest.raises(TaskError) as exc_info:
            service.render("missing", {})
        assert exc_info.value.code == ErrorCode.PROMPT_NOT_FOUND


# ===========================================================================
# Test error codes
# ===========================================================================

class TestPromptErrorCodes:
    def test_prompt_not_found(self):
        assert ErrorCode.PROMPT_NOT_FOUND == 9004

    def test_prompt_path_invalid(self):
        assert ErrorCode.PROMPT_PATH_INVALID == 9005

    def test_prompt_write_failed(self):
        assert ErrorCode.PROMPT_WRITE_FAILED == 9006

    def test_make_error_9xxx(self):
        err = make_error(9004, "Not found")
        assert isinstance(err, TaskError)
        assert err.code == 9004