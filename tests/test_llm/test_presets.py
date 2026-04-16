"""Tests for preset loader & resolve_llm_config."""
import os

import pytest

from newsbrief.llm.presets import (
    get_default_preset_id,
    get_preset,
    load_presets,
    resolve_llm_config,
)


def test_load_presets_has_expected_providers():
    presets = load_presets()
    assert "groq" in presets
    assert "gemini" in presets
    assert "anthropic" in presets
    assert "openrouter" in presets
    assert "openai" in presets


def test_groq_is_default():
    assert get_default_preset_id() == "groq"
    g = get_preset("groq")
    assert g is not None
    assert g.get("default") is True
    assert g["provider"] == "openai_compatible"
    assert g["base_url"].startswith("https://api.groq.com")


def test_get_preset_unknown_returns_none():
    assert get_preset("totally-not-real") is None


def test_resolve_groq_uses_recommended_model():
    resolved = resolve_llm_config({"preset": "groq", "api_key": "sk-test"})
    assert resolved["provider"] == "openai_compatible"
    assert resolved["base_url"] == "https://api.groq.com/openai/v1"
    assert resolved["model"] == "llama-3.3-70b-versatile"
    assert resolved["api_key"] == "sk-test"
    assert resolved["cost_in"] == 0
    assert resolved["cost_out"] == 0


def test_resolve_user_model_override():
    resolved = resolve_llm_config({
        "preset": "groq",
        "api_key": "sk",
        "model": "llama-3.1-8b-instant",
    })
    assert resolved["model"] == "llama-3.1-8b-instant"


def test_resolve_expands_env_var(monkeypatch):
    monkeypatch.setenv("MY_KEY", "secret-123")
    resolved = resolve_llm_config({"preset": "groq", "api_key": "${MY_KEY}"})
    assert resolved["api_key"] == "secret-123"


def test_resolve_falls_back_to_conventional_env(monkeypatch):
    monkeypatch.delenv("NEWSBRIEF_GROQ_API_KEY", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "abc")
    resolved = resolve_llm_config({"preset": "groq"})
    assert resolved["api_key"] == "abc"


def test_resolve_anthropic_includes_costs():
    resolved = resolve_llm_config({"preset": "anthropic", "api_key": "k"})
    assert resolved["provider"] == "anthropic"
    assert resolved["model"] == "claude-haiku-4-5"
    assert resolved["cost_in"] == 1.00
    assert resolved["cost_out"] == 5.00


def test_resolve_openrouter():
    resolved = resolve_llm_config({"preset": "openrouter", "api_key": "k"})
    assert resolved["provider"] == "openrouter"
    assert resolved["base_url"] == "https://openrouter.ai/api/v1"


def test_resolve_none_returns_defaults():
    resolved = resolve_llm_config(None)
    assert resolved["temperature"] == 0.7
    assert resolved["max_tokens"] == 400
