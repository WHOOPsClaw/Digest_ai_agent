"""Native Anthropic Claude Messages API adapter.

Uses httpx directly (no anthropic SDK dependency).
"""
from __future__ import annotations

import time
from typing import Any

import httpx

from newsbrief.llm.base import LLMProvider, LLMResponse

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"


class AnthropicProvider(LLMProvider):
    """Calls POST https://api.anthropic.com/v1/messages."""

    provider_id = "anthropic"

    def __init__(
        self,
        api_key: str,
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 400,
        headers: dict | None = None,
        params: dict | None = None,
        cost_in: float = 0.0,
        cost_out: float = 0.0,
        base_url: str = ANTHROPIC_URL,
        timeout: float = 60.0,
        client: httpx.Client | None = None,
        **_: Any,
    ) -> None:
        self.api_key = api_key or ""
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.extra_headers = dict(headers or {})
        self.extra_params = dict(params or {})
        self.cost_in = cost_in
        self.cost_out = cost_out
        self.base_url = base_url
        self.timeout = timeout
        self._client = client

    def _http(self) -> httpx.Client:
        return self._client or httpx.Client(timeout=self.timeout)

    def generate(
        self,
        prompt: str,
        max_tokens: int | None = None,
        temperature: float | None = None,
        **_: Any,
    ) -> LLMResponse:
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "Content-Type": "application/json",
        }
        headers.update(self.extra_headers)

        body: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens if max_tokens is not None else self.max_tokens,
            "temperature": temperature if temperature is not None else self.temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        body.update(self.extra_params)

        start = time.perf_counter()
        client = self._http()
        try:
            resp = client.post(self.base_url, headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()
        finally:
            if self._client is None:
                client.close()
        latency_ms = int((time.perf_counter() - start) * 1000)

        try:
            content = data.get("content") or []
            text = ""
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text += block.get("text", "")
        except Exception as e:
            raise RuntimeError(f"Unexpected response shape: {data!r}") from e

        usage = data.get("usage") or {}
        tokens_in = int(usage.get("input_tokens", 0) or 0)
        tokens_out = int(usage.get("output_tokens", 0) or 0)
        cost_usd = (tokens_in * self.cost_in + tokens_out * self.cost_out) / 1_000_000

        return LLMResponse(
            text=text.strip(),
            model=data.get("model", self.model),
            latency_ms=latency_ms,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost_usd,
        )
