"""Tests for LLMRouter — task routing + fallback chain."""
import pytest

from newsbrief.llm.base import LLMProvider, LLMResponse
from newsbrief.llm.router import LLMRouter, build_provider


class FakeProvider(LLMProvider):
    provider_id = "fake"

    def __init__(self, name: str, should_fail: bool = False):
        self.name = name
        self.should_fail = should_fail
        self.calls = 0

    def generate(self, prompt: str, **kwargs) -> LLMResponse:
        self.calls += 1
        if self.should_fail:
            raise RuntimeError(f"{self.name} failed")
        return LLMResponse(
            text=f"{self.name}:{prompt}",
            model=self.name,
            latency_ms=1,
            tokens_in=1,
            tokens_out=1,
        )


def _make_router(providers: dict, routing: dict | None = None, fallback=None, primary=None):
    """Bypass build_provider by directly injecting providers into a router."""
    router = LLMRouter.__new__(LLMRouter)
    router._providers = providers
    router._routing = routing or {}
    router._fallback_chain = list(fallback) if fallback is not None else [
        n for n in providers if n != (primary or next(iter(providers)))
    ]
    router._primary = primary or next(iter(providers))
    return router


def test_router_routes_task_to_configured_provider():
    fast = FakeProvider("fast")
    smart = FakeProvider("smart")
    router = _make_router(
        {"fast": fast, "smart": smart},
        routing={"synthesis": "smart", "classification": "fast"},
        fallback=[],
        primary="fast",
    )
    r = router.generate("hello", task="synthesis")
    assert r.model == "smart"
    assert smart.calls == 1
    assert fast.calls == 0

    r2 = router.generate("x", task="classification")
    assert r2.model == "fast"


def test_router_falls_back_on_error():
    broken = FakeProvider("broken", should_fail=True)
    backup = FakeProvider("backup")
    router = _make_router(
        {"broken": broken, "backup": backup},
        routing={"synthesis": "broken"},
        fallback=["backup"],
        primary="broken",
    )
    r = router.generate("hi", task="synthesis")
    assert r.model == "backup"
    assert broken.calls == 1
    assert backup.calls == 1


def test_router_raises_if_all_fail():
    a = FakeProvider("a", should_fail=True)
    b = FakeProvider("b", should_fail=True)
    router = _make_router({"a": a, "b": b}, fallback=["b"], primary="a")
    with pytest.raises(RuntimeError):
        router.generate("hi")


def test_router_primary_used_when_no_routing():
    p = FakeProvider("primary")
    router = _make_router({"primary": p}, primary="primary")
    r = router.generate("hi", task="whatever")
    assert r.model == "primary"


def test_build_provider_openai_compatible():
    p = build_provider({
        "provider": "openai_compatible",
        "base_url": "https://x/v1",
        "api_key": "k",
        "model": "m",
    })
    assert p.provider_id == "openai_compatible"
    assert p.base_url == "https://x/v1"
    assert p.model == "m"


def test_build_provider_anthropic():
    p = build_provider({
        "provider": "anthropic",
        "api_key": "k",
        "model": "claude-haiku-4-5",
    })
    assert p.provider_id == "anthropic"


def test_build_provider_openrouter():
    p = build_provider({
        "provider": "openrouter",
        "base_url": "https://openrouter.ai/api/v1",
        "api_key": "k",
        "model": "x/y",
    })
    assert p.provider_id == "openrouter"


def test_build_provider_unknown_raises():
    with pytest.raises(ValueError):
        build_provider({"provider": "martian-llm", "api_key": "", "model": ""})


def test_router_from_simple_config():
    """Router built from a dict with a preset should work end-to-end."""
    router = LLMRouter({
        "preset": "groq",
        "api_key": "sk-fake",
        "model": "llama-3.3-70b-versatile",
    })
    assert router.primary.provider_id == "openai_compatible"
    assert router.primary.model == "llama-3.3-70b-versatile"
