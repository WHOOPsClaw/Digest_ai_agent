"""Multi-provider routing + fallback chain.

Typical config shapes supported:

    # Simple: single preset
    llm:
      preset: groq
      api_key: ${GROQ_API_KEY}
      model: llama-3.3-70b-versatile

    # Multi-provider:
    llm:
      providers:
        fast:   {preset: groq, model: llama-3.1-8b-instant, api_key: ${GROQ_API_KEY}}
        smart:  {preset: anthropic, model: claude-haiku-4-5, api_key: ${ANTHROPIC_API_KEY}}
      routing:
        synthesis: smart
        classification: fast
      fallback: [fast]
"""
from __future__ import annotations

import logging
from typing import Any

from newsbrief.llm.anthropic import AnthropicProvider
from newsbrief.llm.base import LLMProvider, LLMResponse, get_plugin_provider, load_plugins
from newsbrief.llm.openai_compat import OpenAICompatibleProvider
from newsbrief.llm.openrouter import OpenRouterProvider
from newsbrief.llm.presets import resolve_llm_config

logger = logging.getLogger(__name__)


def build_provider(resolved: dict) -> LLMProvider:
    """Instantiate a provider from a resolved config dict."""
    provider_id = (resolved.get("provider") or "").lower()

    common = {
        "api_key": resolved.get("api_key") or "",
        "model": resolved.get("model") or "",
        "temperature": resolved.get("temperature", 0.7),
        "max_tokens": resolved.get("max_tokens", 400),
        "headers": resolved.get("headers") or {},
        "params": resolved.get("params") or {},
        "cost_in": resolved.get("cost_in", 0.0),
        "cost_out": resolved.get("cost_out", 0.0),
    }

    if provider_id == "anthropic":
        return AnthropicProvider(**common)
    if provider_id == "openrouter":
        return OpenRouterProvider(
            base_url=resolved.get("base_url") or "https://openrouter.ai/api/v1",
            **common,
        )
    if provider_id in ("openai_compatible", "openai", "", None):
        return OpenAICompatibleProvider(
            base_url=resolved.get("base_url") or "",
            **common,
        )

    # Try plugin registry.
    plugins = load_plugins()
    cls = plugins.get(provider_id) or get_plugin_provider(provider_id)
    if cls is not None:
        return cls(**common, base_url=resolved.get("base_url") or "")

    raise ValueError(f"Unknown LLM provider: {provider_id!r}")


class LLMRouter:
    """Routes generate() calls to the right provider per task, with fallback."""

    def __init__(self, config: Any) -> None:
        """Accepts a NewsbriefConfig, its .llm sub-config, or a dict."""
        llm_cfg = getattr(config, "llm", config)
        self._providers: dict[str, LLMProvider] = {}
        self._routing: dict[str, str] = {}
        self._fallback_chain: list[str] = []
        self._primary: str = ""

        # Multi-provider case.
        providers_map = None
        routing_map = None
        fallback = None
        if hasattr(llm_cfg, "providers"):
            providers_map = getattr(llm_cfg, "providers", None)
            routing_map = getattr(llm_cfg, "routing", None)
        elif isinstance(llm_cfg, dict):
            providers_map = llm_cfg.get("providers")
            routing_map = llm_cfg.get("routing")
            fallback = llm_cfg.get("fallback")

        if providers_map:
            for name, sub in providers_map.items():
                resolved = resolve_llm_config(sub)
                self._providers[name] = build_provider(resolved)
            self._primary = next(iter(self._providers))
            self._routing = dict(routing_map or {})
            if fallback:
                self._fallback_chain = list(fallback)
            else:
                # Default fallback: all other providers.
                self._fallback_chain = [
                    n for n in self._providers if n != self._primary
                ]
        else:
            resolved = resolve_llm_config(llm_cfg)
            provider = build_provider(resolved)
            self._providers["primary"] = provider
            self._primary = "primary"

    @property
    def primary(self) -> LLMProvider:
        return self._providers[self._primary]

    def get(self, name: str) -> LLMProvider | None:
        return self._providers.get(name)

    def _pick(self, task: str) -> list[str]:
        """Return ordered list of provider names to try for `task`."""
        primary_name = self._routing.get(task, self._primary)
        chain = [primary_name]
        for fb in self._fallback_chain:
            if fb not in chain and fb in self._providers:
                chain.append(fb)
        # Ensure every name exists.
        return [n for n in chain if n in self._providers]

    def generate(
        self,
        prompt: str,
        task: str = "synthesis",
        **kwargs: Any,
    ) -> LLMResponse:
        chain = self._pick(task)
        if not chain:
            raise RuntimeError("No LLM providers configured.")

        last_err: Exception | None = None
        for name in chain:
            provider = self._providers[name]
            try:
                return provider.generate(prompt, **kwargs)
            except Exception as e:
                logger.warning("LLM provider %r failed: %s", name, e)
                last_err = e
        assert last_err is not None
        raise last_err

    def test(self) -> dict:
        return self.primary.test()
