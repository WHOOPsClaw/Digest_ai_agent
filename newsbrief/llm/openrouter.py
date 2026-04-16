"""OpenRouter provider — thin wrapper over OpenAICompatibleProvider.

Adds the optional HTTP-Referer / X-Title headers recommended by OpenRouter so
usage shows up attributed to newsbrief.
"""
from __future__ import annotations

from typing import Any

from newsbrief.llm.openai_compat import OpenAICompatibleProvider

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterProvider(OpenAICompatibleProvider):
    provider_id = "openrouter"

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = OPENROUTER_BASE_URL,
        http_referer: str = "https://github.com/newsbrief/newsbrief",
        x_title: str = "newsbrief",
        headers: dict | None = None,
        **kwargs: Any,
    ) -> None:
        merged_headers = {
            "HTTP-Referer": http_referer,
            "X-Title": x_title,
        }
        if headers:
            merged_headers.update(headers)
        super().__init__(
            base_url=base_url,
            api_key=api_key,
            model=model,
            headers=merged_headers,
            **kwargs,
        )
