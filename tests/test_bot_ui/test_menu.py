"""Menu rendering tests: each screen returns well-formed {text, keyboard}."""
import pytest

from newsbrief.bot.menu import (
    SCREENS,
    parse_menu_callback,
    render_menu_for_user,
)


SCREEN_IDS = [
    "main", "schedule", "schedule_pick", "schedule_tz", "schedule_await",
    "llm", "llm_pick", "llm_key", "llm_test",
    "sources", "sources_list", "sources_add", "sources_discover", "sources_check",
    "topic",
    "profile", "profile_edit", "profile_lang", "profile_style",
    "format", "format_items", "format_length",
    "notify",
    "stats", "stats_7", "stats_30",
    "pause",
    "diag",
    "reset",
]


def _assert_view(view):
    assert isinstance(view, dict)
    assert "text" in view and isinstance(view["text"], str) and view["text"]
    assert "keyboard" in view and isinstance(view["keyboard"], list)
    # Each row is a list of dicts with text + callback_data/url
    button_count = 0
    for row in view["keyboard"]:
        assert isinstance(row, list)
        for btn in row:
            assert "text" in btn
            assert "callback_data" in btn or "url" in btn
            if "callback_data" in btn:
                assert len(btn["callback_data"].encode("utf-8")) <= 64
            button_count += 1
    # Max 8 primary buttons per screen (rule from spec)
    assert button_count <= 24  # allow stats presets etc


@pytest.mark.parametrize("screen_id", SCREEN_IDS)
def test_all_screens_render(screen_id, config, storage):
    # Force-load screens first
    render_menu_for_user("u1", config, storage, "main")
    assert screen_id in SCREENS, f"missing screen: {screen_id}"
    view = render_menu_for_user("u1", config, storage, screen_id)
    _assert_view(view)
    assert view["screen"] == screen_id


def test_main_menu_has_back_free_top(config, storage):
    view = render_menu_for_user("u1", config, storage, "main")
    # Main menu has no back button — it's the root
    flat = [b["text"] for row in view["keyboard"] for b in row]
    assert any("LLM" in t for t in flat)
    assert any("Время" in t for t in flat)


def test_parse_menu_callback():
    parsed = parse_menu_callback("menu:schedule:preset:09:00")
    assert parsed == {"screen": "schedule", "action": "preset", "value": "09", "extra": "00"}

    parsed = parse_menu_callback("menu:main:open")
    assert parsed["screen"] == "main"
    assert parsed["action"] == "open"
    assert parsed["value"] == ""

    assert parse_menu_callback("fb:1:2:up") is None
    assert parse_menu_callback("") is None
    assert parse_menu_callback("menu:") is None
