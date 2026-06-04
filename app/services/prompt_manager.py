from __future__ import annotations

import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog

from app.core.config import get_settings

logger = structlog.get_logger("services.prompt_manager")

_VARIABLE_PATTERN = re.compile(r"\{\{(\w+)\}\}")


def extract_variables(content: str) -> list[str]:
    """Extract {{variable}} placeholders from template content."""
    return list(dict.fromkeys(_VARIABLE_PATTERN.findall(content)))


class PromptManager:
    """Manages prompt template loading, caching, seeding, and rendering.

    Responsibilities:
    - Load prompt files from prompts/ directory at startup
    - Cache all templates in memory (no hot-reload)
    - Seed missing prompt files from prompts_default/
    - Provide get/set interface for domain service layer

    Does NOT handle PG persistence — that's the domain service's job.
    """

    def __init__(self, prompts_dir: str | None = None, prompts_default_dir: str | None = None) -> None:
        settings = get_settings()
        self._prompts_dir = Path(prompts_dir or settings.prompt_config.prompts_dir)
        self._prompts_default_dir = Path(prompts_default_dir or settings.prompt_config.prompts_default_dir)
        self._cache: dict[str, dict[str, str]] = {}

    @property
    def prompts_dir(self) -> Path:
        return self._prompts_dir

    @property
    def prompts_default_dir(self) -> Path:
        return self._prompts_default_dir

    def seed_defaults(self) -> dict[str, str]:
        """Seed missing prompt files from prompts_default/ to prompts/.

        Returns a dict of {name: status} where status is 'seeded' or 'already_exists'.
        """
        results: dict[str, str] = {}

        if not self._prompts_default_dir.is_dir():
            logger.warning("prompt_manager.no_default_dir", path=str(self._prompts_default_dir))
            return results

        for md_file in self._prompts_default_dir.rglob("*.md"):
            rel_path = md_file.relative_to(self._prompts_default_dir)
            target = self._prompts_dir / rel_path
            name = str(rel_path.with_suffix("")).replace(os.sep, "/")

            if not target.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(md_file), str(target))
                results[name] = "seeded"
                logger.info("prompt_manager.seeded", name=name, target=str(target))
            else:
                results[name] = "already_exists"

        return results

    def preload(self) -> int:
        """Load all prompt files from prompts/ into memory cache.

        Returns the number of templates loaded.
        """
        self._cache.clear()

        if not self._prompts_dir.is_dir():
            logger.warning("prompt_manager.no_prompts_dir", path=str(self._prompts_dir))
            return 0

        count = 0
        for md_file in self._prompts_dir.rglob("*.md"):
            rel_path = md_file.relative_to(self._prompts_dir)
            name = str(rel_path.with_suffix("")).replace(os.sep, "/")
            directory = str(rel_path.parent).replace(os.sep, "/") if rel_path.parent != Path(".") else ""

            try:
                content = md_file.read_text(encoding="utf-8")
            except Exception as exc:
                logger.warning("prompt_manager.load_failed", name=name, error=str(exc))
                continue

            self._cache[name] = {
                "name": name,
                "directory": directory,
                "content": content,
                "path": str(md_file),
            }
            count += 1

        logger.info("prompt_manager.preloaded", count=count)
        return count

    def get_cached(self, name: str) -> str | None:
        """Get prompt content from memory cache by name.

        Name can be:
        - flat: "rag_answer"
        - with directory: "skills/rag_answer"
        """
        if name in self._cache:
            return self._cache[name].get("content")
        for key, entry in self._cache.items():
            if key.endswith(f"/{name}") or key == name:
                return entry.get("content")
        return None

    def load_from_file(self, name: str) -> str | None:
        """Load prompt content directly from file (not from cache).

        Used for baseline/reset operations.
        """
        entry = self._cache.get(name)
        if entry:
            path = Path(entry["path"])
            if path.is_file():
                return path.read_text(encoding="utf-8")

        for md_file in self._prompts_dir.rglob("*.md"):
            rel_path = md_file.relative_to(self._prompts_dir)
            file_name = str(rel_path.with_suffix(""))
            if file_name == name or file_name.endswith(f"/{name}"):
                return md_file.read_text(encoding="utf-8")

        default_path = self._prompts_default_dir / f"{name}.md"
        if default_path.is_file():
            return default_path.read_text(encoding="utf-8")

        return None

    def update_cache(self, name: str, content: str, directory: str = "") -> None:
        """Update a prompt in the memory cache after DB modification."""
        self._cache[name] = {
            "name": name,
            "directory": directory,
            "content": content,
            "path": self._cache.get(name, {}).get("path", ""),
        }

    def list_cached(self) -> dict[str, dict[str, str]]:
        """Return the full cache (for inspection/debugging)."""
        return dict(self._cache)

    def render(self, name: str, variables: dict[str, Any] | None = None) -> str:
        """Render a prompt template by replacing {{variable}} placeholders.

        Raises KeyError if template not found.
        """
        content = self.get_cached(name)
        if content is None:
            raise KeyError(f"Prompt template '{name}' not found in cache")

        if variables:
            for var_name, var_value in variables.items():
                content = content.replace(f"{{{{{var_name}}}}}", str(var_value))

        return content

    def get_directory(self, name: str) -> str:
        """Get the directory of a cached prompt."""
        entry = self._cache.get(name)
        if entry:
            return entry.get("directory", "")
        for key, val in self._cache.items():
            if key.endswith(f"/{name}"):
                return val.get("directory", "")
        return ""

    def validate_name(self, name: str) -> bool:
        """Validate that a prompt name doesn't contain path traversal or illegal chars."""
        if not name:
            return False
        if ".." in name:
            return False
        if "/" in name and ".." in name:
            return False
        import re as _re
        if _re.search(r'[<>"|\\?\x00-\x1f]', name):
            return False
        return True