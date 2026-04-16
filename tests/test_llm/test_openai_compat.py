"""Tests for OpenAICompatibleProvider — mock httpx to verify request shape."""
import json

import httpx
import pytest

from newsbrief.llm.anthropic import AnthropicProvider
from newsbrief.llm.openai_compat import OpenAICompatibleProvider
from newsbrief.llm.openrouter import OpenRouterProvider


def _mock_client(handler):
    transport = httpx.MockTransport(handler)
    return httpx.Client(transport=transport)


def test_openai_compat_request_shape_and_parsing():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(
            200,
            json={
                "id": "x",
                "model": "llama-3.3-70b-versatile",
                "choices": [
                    {"message": {"role": "assistant", "content": "OK"}, "finish_reason": "stop"}
                ],
                "usage": {"prompt_tokens": 12, "completion_tokens": 3, "total_tokens": 15},
            },
        )

    provider = OpenAICompatibleProvider(
        base_url="https://api.groq.com/openai/v1",
        api_key="sk-test",
        model="llama-3.3-70b-versatile",
        temperature=0.5,
        max_tokens=50,
        cost_in=0.0,
        cost_out=0.0,
        client=_mock_client(handler),
    )

    resp = provider.generate("Say OK in one word.")

    assert resp.text == "OK"
    assert resp.model == "llama-3.3-70b-versatile"
    assert resp.tokens_in == 12
    assert resp.tokens_out == 3
    assert resp.cost_usd == 0.0
    assert resp.latency_ms >= 0

    assert captured["url"] == "https://api.groq.com/openai/v1/chat/completions"
    assert captured["headers"]["authorization"] == "Bearer sk-test"
    assert captured["headers"]["content-type"] == "application/json"

    body = captured["body"]
    assert body["model"] == "llama-3.3-70b-versatile"
    assert body["messages"] == [{"role": "user", "content": "Say OK in one word."}]
    assert body["temperature"] == 0.5
    assert body["max_tokens"] == 50


def test_openai_compat_cost_calculation():
    def handler(request):
        return httpx.Response(200, json={
            "model": "gpt-4o-mini",
            "choices": [{"message": {"content": "Hi"}}],
            "usage": {"prompt_tokens": 1_000_000, "completion_tokens": 1_000_000},
        })

    provider = OpenAICompatibleProvider(
        base_url="https://api.openai.com/v1",
        api_key="sk",
        model="gpt-4o-mini",
        cost_in=0.15,
        cost_out=0.60,
        client=_mock_client(handler),
    )
    resp = provider.generate("hi")
    assert resp.cost_usd == pytest.approx(0.75)


def test_openai_compat_extra_headers_and_params():
    captured = {}

    def handler(request):
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(200, json={
            "model": "m",
            "choices": [{"message": {"content": "x"}}],
            "usage": {},
        })

    provider = OpenAICompatibleProvider(
        base_url="https://x/v1",
        api_key="k",
        model="m",
        headers={"X-Custom": "yes"},
        params={"top_p": 0.9},
        client=_mock_client(handler),
    )
    provider.generate("p", max_tokens=7, temperature=0.2)
    assert captured["headers"]["x-custom"] == "yes"
    assert captured["body"]["top_p"] == 0.9
    assert captured["body"]["max_tokens"] == 7
    assert captured["body"]["temperature"] == 0.2


def test_openai_compat_http_error_raises():
    def handler(request):
        return httpx.Response(401, json={"error": "bad key"})

    provider = OpenAICompatibleProvider(
        base_url="https://x/v1",
        api_key="bad",
        model="m",
        client=_mock_client(handler),
    )
    with pytest.raises(httpx.HTTPStatusError):
        provider.generate("hi")


def test_openai_compat_test_method_returns_ok():
    def handler(request):
        return httpx.Response(200, json={
            "model": "m",
            "choices": [{"message": {"content": "OK"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        })

    provider = OpenAICompatibleProvider(
        base_url="https://x/v1", api_key="k", model="m",
        client=_mock_client(handler),
    )
    result = provider.test()
    assert result["ok"] is True
    assert result["model"] == "m"


def test_openai_compat_test_method_returns_error():
    def handler(request):
        return httpx.Response(500, json={"error": "server"})

    provider = OpenAICompatibleProvider(
        base_url="https://x/v1", api_key="k", model="m",
        client=_mock_client(handler),
    )
    result = provider.test()
    assert result["ok"] is False
    assert "error" in result


def test_anthropic_request_shape():
    captured = {}

    def handler(request):
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(200, json={
            "id": "msg_1",
            "model": "claude-haiku-4-5",
            "content": [{"type": "text", "text": "OK"}],
            "usage": {"input_tokens": 5, "output_tokens": 1},
        })

    provider = AnthropicProvider(
        api_key="k-ant",
        model="claude-haiku-4-5",
        cost_in=1.00,
        cost_out=5.00,
        client=_mock_client(handler),
    )
    resp = provider.generate("hi")
    assert resp.text == "OK"
    assert resp.tokens_in == 5
    assert resp.tokens_out == 1
    assert captured["url"] == "https://api.anthropic.com/v1/messages"
    assert captured["headers"]["x-api-key"] == "k-ant"
    assert captured["headers"]["anthropic-version"] == "2023-06-01"
    assert captured["body"]["messages"] == [{"role": "user", "content": "hi"}]


def test_openrouter_adds_attribution_headers():
    captured = {}

    def handler(request):
        captured["headers"] = dict(request.headers)
        return httpx.Response(200, json={
            "model": "m",
            "choices": [{"message": {"content": "OK"}}],
            "usage": {},
        })

    provider = OpenRouterProvider(
        api_key="k",
        model="google/gemini-2.0-flash-exp:free",
        client=_mock_client(handler),
    )
    provider.generate("hi")
    assert captured["headers"]["http-referer"]
    assert captured["headers"]["x-title"] == "newsbrief"
