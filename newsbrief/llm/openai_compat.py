"""OpenAI Chat Completions compatible adapter.

Works with any provider exposing the OpenAI `/chat/completions` surface:
Groq, Google Gemini (OpenAI-compat endpoint), Cerebras, Mistral, OpenAI,
DeepSeek, Together, Fireworks, etc.
"""
from __future__ import annotations

import time
from typing import Any

import httpx

from newsbrief.llm.base import LLMProvider, LLMResponse


class OpenAICompatibleProvider(LLMProvider):
    """POST {base_url}/chat/completions and parse the standard response."""

    provider_id = "openai_compatible"

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 400,
        headers: dict | None = None,
        params: dict | None = None,
        cost_in: float = 0.0,
        cost_out: float = 0.0,
        timeout: float = 60.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = api_key or ""
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.extra_headers = dict(headers or {})
        self.extra_params = dict(params or {})
        self.cost_in = cost_in
        self.cost_out = cost_out
        self.timeout = timeout
        self._client = client  # allow injection for tests

    def _http(self) -> httpx.Client:
        return self._client or httpx.Client(timeout=self.timeout)

    def _build_request(
        self,
        prompt: str,
        max_tokens: int | None,
        temperature: float | None,
    ) -> tuple[str, dict, dict]:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        headers.update(self.extra_headers)
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature if temperature is not None else self.temperature,
            "max_tokens": max_tokens if max_tokens is not None else self.max_tokens,
        }
        body.update(self.extra_params)
        return url, headers, body

    def generate(
        self,
        prompt: str,
        max_tokens: int | None = None,
        temperature: float | None = None,
        **_: Any,
    ) -> LLMResponse:
        url, headers, body = self._build_request(prompt, max_tokens, temperature)

        start = time.perf_counter()
        client = self._http()
        try:
            resp = client.post(url, headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()
        finally:
            if self._client is None:
                client.close()
        latency_ms = int((time.perf_counter() - start) * 1000)

        try:
            text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as e:
            raise RuntimeError(f"Unexpected response shape: {data!r}") from e

        usage = data.get("usage") or {}
        tokens_in = int(usage.get("prompt_tokens", 0) or 0)
        tokens_out = int(usage.get("completion_tokens", 0) or 0)
        # cost_in/out are per 1M tokens (USD).
        cost_usd = (tokens_in * self.cost_in + tokens_out * self.cost_out) / 1_000_000

        return LLMResponse(
            text=text.strip(),
            model=data.get("model", self.model),
            latency_ms=latency_ms,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost_usd,
        )
