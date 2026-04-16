"""Tests for multi-provider LLM Telegram screens."""
from __future__ import annotations

from newsbrief.bot import fsm
from newsbrief.bot.menu import handle_callback, render_menu_for_user
from newsbrief.config import SingleLLMConfig
from newsbrief.llm import manager as llm_manager


def _seed(config):
    llm_manager.add_provider(
        config, "groq_free",
        SingleLLMConfig(preset="groq", api_key="k1", model="llama-3.3-70b-versatile",
                        display_name="Groq"),
    )
    llm_manager.add_provider(
        config, "anthropic",
        SingleLLMConfig(preset="anthropic", api_key="k2", model="claude-haiku-4-5",
                        display_name="Claude"),
    )
    llm_manager.set_active(config, "groq_free")


def test_llm_screen_shows_active(config, storage):
    _seed(config)
    view = render_menu_for_user("u1", config, storage, "llm")
    assert "LLM провайдер" in view["text"]
    assert "Groq" in view["text"]
    assert "активный" in view["text"].lower() or "Активный" in view["text"]


def test_llm_switch_screen_lists_providers(config, storage):
    _seed(config)
    view = render_menu_for_user("u1", config, storage, "llm_switch")
    # Both providers appear in button labels.
    labels = [btn["text"] for row in view["keyboard"] for btn in row]
    joined = " | ".join(labels)
    assert "Groq" in joined
    assert "Claude" in joined


def test_llm_switch_set_changes_active(config, storage):
    _seed(config)
    render_menu_for_user("u1", config, storage, "main")
    handle_callback("u1", "menu:llm_switch:set:anthropic", config, storage)
    assert config.llm.active == "anthropic"


def test_llm_add_flow_fsm_preset_key(config, storage):
    render_menu_for_user("u1", config, storage, "main")
    view = handle_callback("u1", "menu:llm_add:pick:groq", config, storage)
    assert view["screen"] == "llm_add_key"
    state, ctx = fsm.get_user_state("u1", storage)
    assert state == "awaiting_llm_add_key:groq"
    assert ctx.get("preset") == "groq"


def test_llm_add_flow_fsm_custom(config, storage):
    render_menu_for_user("u1", config, storage, "main")
    view = handle_callback("u1", "menu:llm_add:pick:custom", config, storage)
    assert view["screen"] == "llm_add_custom"
    state, ctx = fsm.get_user_state("u1", storage)
    assert state == "awaiting_llm_add_base_url"
    assert ctx.get("preset") == "custom"


def test_llm_remove_confirm_flow(config, storage):
    _seed(config)
    render_menu_for_user("u1", config, storage, "main")
    view = handle_callback("u1", "menu:llm_remove:ask:anthropic", config, storage)
    assert view["screen"] == "llm_remove_confirm"
    assert "anthropic" in view["text"]

    view = handle_callback("u1", "menu:llm_remove:confirm:anthropic", config, storage)
    assert "anthropic" not in config.llm.providers
    # Active should have been reassigned.
    assert config.llm.active == "groq_free"


def test_llm_test_all_lists_providers(config, storage, monkeypatch):
    _seed(config)
    # Stub the per-provider test to avoid network calls.
    monkeypatch.setattr(
        llm_manager, "test_provider",
        lambda cfg, pid: {"ok": True, "latency_ms": 42, "error": None},
    )
    view = render_menu_for_user("u1", config, storage, "llm_test_all")
    assert "Groq" in view["text"]
    assert "Claude" in view["text"]
    assert "42ms" in view["text"]


def test_legacy_preset_switch_still_works(config, storage):
    """Backward compat: old menu:llm:preset:<id> path still functional."""
    render_menu_for_user("u1", config, storage, "main")
    view = handle_callback("u1", "menu:llm:preset:together", config, storage)
    assert config.llm.preset == "together"
    assert view["screen"] == "llm_key"
    state, _ = fsm.get_user_state("u1", storage)
    assert state == "awaiting_llm_key:together"
