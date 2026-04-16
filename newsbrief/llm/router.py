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
import time
from typing import Any

import httpx

from newsbrief.llm.anthropic import AnthropicProvider
from newsbrief.llm.base import LLMProvider, LLMResponse, get_plugin_provider, load_plugins
from newsbrief.llm.openai_compat import OpenAICompatibleProvider
from newsbrief.llm.openrouter import OpenRouterProvider
from newsbrief.llm.presets import get_preset, resolve_llm_config
from newsbrief.llm.rate_limiter import (
    LLMRateLimitError,
    MAX_RETRIES,
    TokenBucket,
    compute_retry_delay,
)

logger = logging.getLogger(__name__)


def _parse_retry_after(resp: httpx.Response) -> float | None:
    """Extract Retry-After header (seconds). Returns None if absent/invalid."""
    ra = resp.headers.get("Retry-After") if resp is not None else None
    if not ra:
        return None
    try:
        return float(ra)
    except (TypeError, ValueError):
        return None


class RateLimitedProvider(LLMProvider):
    """Wraps a raw LLMProvider with a token bucket + 429 retry logic.

    - Before each call: bucket.acquire() blocks until a slot is free.
    - On httpx 429 (or LLMRateLimitError from inner): exponential backoff
      (0s → 5s → 15s → 45s, up to 4 attempts). Respects Retry-After header.
    - Other exceptions propagate on the first attempt.
    """

    provider_id = "rate_limited"

    def __init__(self, inner: LLMProvider, bucket: TokenBucket | None = None,
                 request_delay_sec: float = 0.0) -> None:
        self._inner = inner
        self._bucket = bucket
        self._request_delay = max(0.0, float(request_delay_sec or 0.0))
        # Expose inner attrs for diagnostics / backward-compat.
        self.model = getattr(inner, "model", "")
        # Mirror provider_id so existing callers see the underlying provider.
        self.provider_id = getattr(inner, "provider_id", "rate_limited")

    def __getattr__(self, name: str) -> Any:
        # Transparent passthrough for any attribute not found locally.
        return getattr(self._inner, name)

    def generate(self, prompt: str, **kwargs: Any) -> LLMResponse:
        last_err: Exception | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            if self._bucket is not None:
                self._bucket.acquire(tokens=1, max_wait=180.0)
            try:
                resp = self._inner.generate(prompt, **kwargs)
                if self._request_delay > 0:
                    time.sleep(self._request_delay)
                return resp
            except httpx.HTTPStatusError as e:
                status = e.response.status_code if e.response is not None else 0
                if status == 429 and attempt < MAX_RETRIES:
                    delay = compute_retry_delay(attempt + 1, _parse_retry_after(e.response))
                    logger.warning(
                        "[llm] 429 from %s, retry %d/%d in %.1fs",
                        getattr(self._inner, "provider_id", "?"),
                        attempt, MAX_RETRIES, delay,
                    )
                    if delay > 0:
                        time.sleep(delay)
                    last_err = e
                    continue
                if status == 429:
                    raise LLMRateLimitError(f"Rate limit exhausted after {attempt} attempts") from e
                raise
            except LLMRateLimitError as e:
                last_err = e
                if attempt < MAX_RETRIES:
                    delay = compute_retry_delay(attempt + 1)
                    if delay > 0:
                        time.sleep(delay)
                    continue
                raise
        # Shouldn't reach here; exhaust all attempts.
        if last_err is not None:
            raise LLMRateLimitError(str(last_err)) from last_err
        raise LLMRateLimitError("Rate limit retries exhausted")

    def test(self) -> dict:
        return self._inner.test()


def _build_bucket_for_preset(preset_id: str | None) -> TokenBucket | None:
    """Read rate_limits from presets.yaml for the given preset."""
    if not preset_id:
        return None
    preset = get_preset(preset_id)
    if not preset:
        return None
    rl = preset.get("rate_limits") or {}
    rpm = rl.get("rpm")
    if not rpm:
        return None
    return TokenBucket(rpm=int(rpm), tpm=rl.get("tpm"), rpd=rl.get("rpd"))


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
        providers_map: Any = None
        routing_map: Any = None
        fallback: Any = None
        active: Any = None
        if hasattr(llm_cfg, "providers"):
            providers_map = getattr(llm_cfg, "providers", None)
            routing_map = getattr(llm_cfg, "routing", None)
            active = getattr(llm_cfg, "active", None)
        elif isinstance(llm_cfg, dict):
            providers_map = llm_cfg.get("providers")
            routing_map = llm_cfg.get("routing")
            fallback = llm_cfg.get("fallback")
            active = llm_cfg.get("active")

        # Pipeline-wide throttle knobs (from llm config).
        request_delay = float(getattr(llm_cfg, "request_delay_sec", 0.0) or 0.0) if not isinstance(llm_cfg, dict) else float(llm_cfg.get("request_delay_sec") or 0.0)

        def _as_dict(v: Any) -> dict:
            if hasattr(v, "model_dump"):
                return v.model_dump()
            if isinstance(v, dict):
                return dict(v)
            return {}

        if providers_map:
            for name, sub in providers_map.items():
                resolved = resolve_llm_config(_as_dict(sub))
                raw = build_provider(resolved)
                bucket = _build_bucket_for_preset(resolved.get("preset_id"))
                self._providers[name] = RateLimitedProvider(
                    raw, bucket=bucket, request_delay_sec=request_delay,
                )
            if active and active in self._providers:
                self._primary = active
            else:
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
            raw = build_provider(resolved)
            bucket = _build_bucket_for_preset(resolved.get("preset_id"))
            provider = RateLimitedProvider(
                raw, bucket=bucket, request_delay_sec=request_delay,
            )
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
