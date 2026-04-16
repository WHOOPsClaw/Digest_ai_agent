"""Base classes for LLM providers.

Defines abstract LLMProvider interface and LLMResponse dataclass. Also provides
a plugin loader that scans `plugins/llm/` for custom providers.
"""
from __future__ import annotations

import importlib.util
import logging
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    """Response from an LLM provider's generate() call."""
    text: str
    model: str
    latency_ms: int
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0


class LLMProvider(ABC):
    """Abstract base for all LLM providers."""

    provider_id: str = "base"

    @abstractmethod
    def generate(self, prompt: str, **kwargs: Any) -> LLMResponse:
        """Generate text for `prompt`. Returns LLMResponse."""
        ...

    def test(self) -> dict:
        """Smoke-test the provider. Returns {ok, latency_ms, model} or {ok:False, error}."""
        try:
            r = self.generate("Say OK in one word.", max_tokens=10)
            return {
                "ok": True,
                "latency_ms": r.latency_ms,
                "model": r.model,
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}


# Registry for dynamically-loaded plugin providers: {provider_id: class}
_PLUGIN_REGISTRY: dict[str, type[LLMProvider]] = {}


def register_provider(cls: type[LLMProvider]) -> type[LLMProvider]:
    """Decorator to register a provider class in the plugin registry."""
    _PLUGIN_REGISTRY[cls.provider_id] = cls
    return cls


def get_plugin_provider(provider_id: str) -> type[LLMProvider] | None:
    """Look up a registered plugin provider by id."""
    return _PLUGIN_REGISTRY.get(provider_id)


def load_plugins(plugins_dir: str | Path = "plugins/llm") -> dict[str, type[LLMProvider]]:
    """Scan `plugins/llm/` for *.py files, import them, and collect LLMProvider subclasses.

    Plugins can either use @register_provider decorator or simply define a subclass of
    LLMProvider with a `provider_id` attribute — the loader picks them up either way.
    """
    path = Path(plugins_dir)
    if not path.exists() or not path.is_dir():
        return dict(_PLUGIN_REGISTRY)

    for py_file in sorted(path.glob("*.py")):
        if py_file.name.startswith("_"):
            continue
        mod_name = f"newsbrief_llm_plugin_{py_file.stem}"
        try:
            spec = importlib.util.spec_from_file_location(mod_name, py_file)
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = module
            spec.loader.exec_module(module)

            # Auto-discover LLMProvider subclasses in the module.
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (
                    isinstance(attr, type)
                    and issubclass(attr, LLMProvider)
                    and attr is not LLMProvider
                ):
                    pid = getattr(attr, "provider_id", None)
                    if pid and pid != "base":
                        _PLUGIN_REGISTRY[pid] = attr
        except Exception as e:
            logger.warning("Failed to load plugin %s: %s", py_file, e)

    return dict(_PLUGIN_REGISTRY)
