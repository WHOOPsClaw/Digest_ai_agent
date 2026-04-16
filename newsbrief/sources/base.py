"""SourceProvider abstraction + plugin loader."""
from __future__ import annotations

import importlib.util
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Iterator

from newsbrief.core.models import RawArticle

logger = logging.getLogger(__name__)


class SourceProvider(ABC):
    """Abstract base class for all source providers."""

    provider_id: str = ""

    @abstractmethod
    def fetch(self, config: dict, limit: int = 20) -> Iterator[RawArticle]:
        """Yield RawArticle objects from this source."""
        ...

    def validate_config(self, config: dict) -> list[str]:
        """Return a list of validation errors (empty if OK)."""
        return []

    def describe(self, config: dict) -> str:
        """Return human-readable description of this source."""
        return f"{self.provider_id}:{config}"


_REGISTRY: dict[str, SourceProvider] = {}


def register(provider: SourceProvider) -> None:
    """Register a provider instance by its provider_id."""
    if not provider.provider_id:
        raise ValueError("provider_id must be set")
    _REGISTRY[provider.provider_id] = provider


def get_provider(provider_id: str) -> SourceProvider | None:
    return _REGISTRY.get(provider_id)


def all_providers() -> dict[str, SourceProvider]:
    return dict(_REGISTRY)


def load_plugins(plugins_dir: str | Path = "plugins/sources") -> list[str]:
    """Scan plugins_dir and import all .py files as plugin modules.

    Each plugin is expected to call register() at import time.
    Returns list of loaded module names.
    """
    loaded: list[str] = []
    path = Path(plugins_dir)
    if not path.exists() or not path.is_dir():
        return loaded

    for py_file in sorted(path.glob("*.py")):
        if py_file.name.startswith("_"):
            continue
        mod_name = f"newsbrief_plugin_{py_file.stem}"
        try:
            spec = importlib.util.spec_from_file_location(mod_name, py_file)
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            loaded.append(mod_name)
            logger.info("loaded source plugin: %s", py_file.name)
        except Exception as e:
            logger.warning("failed to load plugin %s: %s", py_file.name, e)

    return loaded
