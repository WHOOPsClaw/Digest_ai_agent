"""Multi-provider LLM: migration, manager API, router active-switch."""
from __future__ import annotations

from newsbrief.config import LLMConfig, NewsbriefConfig, SingleLLMConfig
from newsbrief.llm.manager import (
    add_provider,
    list_providers,
    remove_provider,
    set_active,
)
from newsbrief.llm.migration import migrate_single_to_multi


def _cfg_with_legacy() -> NewsbriefConfig:
    cfg = NewsbriefConfig()
    cfg.llm = LLMConfig(
        preset="groq",
        model="llama-3.3-70b-versatile",
        api_key="sk-fake",
    )
    return cfg


# -------- migration ----------------------------------------------------------

def test_migration_single_to_multi_populates_default():
    cfg = _cfg_with_legacy()
    assert not cfg.llm.providers

    migrate_single_to_multi(cfg)

    assert "default" in cfg.llm.providers
    assert cfg.llm.active == "default"
    spec = cfg.llm.providers["default"]
    assert spec.preset == "groq"
    assert spec.model == "llama-3.3-70b-versatile"
    assert spec.api_key == "sk-fake"


def test_migration_noop_when_providers_already_populated():
    cfg = NewsbriefConfig()
    cfg.llm = LLMConfig(
        active="smart",
        providers={
            "smart": SingleLLMConfig(preset="anthropic", api_key="x", model="c"),
        },
    )
    migrate_single_to_multi(cfg)
    assert list(cfg.llm.providers.keys()) == ["smart"]
    assert cfg.llm.active == "smart"


def test_backward_compat_resolve_active_legacy():
    # With no providers dict, resolve_active uses legacy root fields.
    cfg = NewsbriefConfig()
    cfg.llm = LLMConfig(preset="groq", api_key="sk-fake", model="m")
    # Do NOT run migration — test the legacy fallback path directly.
    resolved = cfg.llm.resolve_active()
    assert resolved["preset"] == "groq"
    assert resolved["api_key"] == "sk-fake"


def test_resolve_active_multi_provider():
    cfg = NewsbriefConfig()
    cfg.llm = LLMConfig(
        active="b",
        providers={
            "a": SingleLLMConfig(preset="groq", api_key="k1", model="m1"),
            "b": SingleLLMConfig(preset="anthropic", api_key="k2", model="m2"),
        },
    )
    r = cfg.llm.resolve_active()
    assert r["preset"] == "anthropic"
    assert r["api_key"] == "k2"


# -------- manager API --------------------------------------------------------

def test_add_provider_sets_active_on_first():
    cfg = NewsbriefConfig()
    cfg.llm = LLMConfig()  # empty
    add_provider(cfg, "groq_free", SingleLLMConfig(preset="groq", api_key="k", model="m"))
    assert "groq_free" in cfg.llm.providers
    assert cfg.llm.active == "groq_free"


def test_set_active_switches():
    cfg = NewsbriefConfig()
    cfg.llm = LLMConfig(
        providers={
            "a": SingleLLMConfig(preset="groq", api_key="k", model="m"),
            "b": SingleLLMConfig(preset="anthropic", api_key="k2", model="m2"),
        },
        active="a",
    )
    assert set_active(cfg, "b") is True
    assert cfg.llm.active == "b"
    assert set_active(cfg, "nope") is False


def test_remove_provider_reassigns_active():
    cfg = NewsbriefConfig()
    cfg.llm = LLMConfig(
        providers={
            "a": SingleLLMConfig(preset="groq", api_key="k", model="m"),
            "b": SingleLLMConfig(preset="anthropic", api_key="k2", model="m2"),
        },
        active="a",
    )
    assert remove_provider(cfg, "a") is True
    assert "a" not in cfg.llm.providers
    assert cfg.llm.active == "b"


def test_list_providers_marks_active_and_status():
    cfg = NewsbriefConfig()
    cfg.llm = LLMConfig(
        providers={
            "a": SingleLLMConfig(preset="groq", api_key="k", model="m"),
            "b": SingleLLMConfig(preset="anthropic", api_key="", model="m2"),
        },
        active="a",
    )
    out = list_providers(cfg)
    by_id = {p["id"]: p for p in out}
    assert by_id["a"]["active"] is True
    assert by_id["b"]["active"] is False
    assert by_id["a"]["status"] == "ok"
    assert by_id["b"]["status"] == "missing_key"


# -------- router uses active -------------------------------------------------

def test_router_uses_active_provider():
    from newsbrief.llm.router import LLMRouter

    cfg = NewsbriefConfig()
    cfg.llm = LLMConfig(
        providers={
            "fast":  SingleLLMConfig(preset="groq",      api_key="k1", model="llama-3.1-8b-instant"),
            "smart": SingleLLMConfig(preset="anthropic", api_key="k2", model="claude-haiku-4-5"),
        },
        active="smart",
    )
    router = LLMRouter(cfg)
    # Primary resolves to the 'active' entry.
    assert router._primary == "smart"  # noqa: SLF001


def test_router_backward_compat_single_provider_config():
    """Legacy dict config without providers still works via root fields."""
    from newsbrief.llm.router import LLMRouter
    router = LLMRouter({
        "preset": "groq",
        "api_key": "sk-fake",
        "model": "llama-3.3-70b-versatile",
    })
    assert router.primary is not None
