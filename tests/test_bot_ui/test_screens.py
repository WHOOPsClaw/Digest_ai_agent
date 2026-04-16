"""Dispatcher tests: handle_callback navigates and mutates state correctly."""
from newsbrief.bot.menu import handle_callback, render_menu_for_user
from newsbrief.bot import fsm


def test_open_screen(config, storage):
    view = handle_callback("u1", "menu:schedule:open", config, storage)
    assert view["screen"] == "schedule"
    assert "Время доставки" in view["text"]


def test_schedule_preset_sets_config(config, storage):
    # Force-load screens
    render_menu_for_user("u1", config, storage, "main")
    view = handle_callback("u1", "menu:schedule:preset:09:30", config, storage)
    assert config.schedule.send_at == "09:30"
    assert view["screen"] == "schedule"


def test_schedule_custom_sets_fsm(config, storage):
    render_menu_for_user("u1", config, storage, "main")
    handle_callback("u1", "menu:schedule:custom", config, storage)
    state, _ = fsm.get_user_state("u1", storage)
    assert state == "awaiting_schedule_input"


def test_llm_preset_switch(config, storage):
    render_menu_for_user("u1", config, storage, "main")
    view = handle_callback("u1", "menu:llm:preset:together", config, storage)
    assert config.llm.preset == "together"
    assert view["screen"] == "llm_key"
    state, ctx = fsm.get_user_state("u1", storage)
    assert state == "awaiting_llm_key:together"
    assert ctx.get("preset") == "together"


def test_profile_lang_set(config, storage):
    render_menu_for_user("u1", config, storage, "main")
    handle_callback("u1", "menu:profile:lang_set:en", config, storage)
    assert config.user.language == "en"


def test_profile_style_set(config, storage):
    render_menu_for_user("u1", config, storage, "main")
    handle_callback("u1", "menu:profile:style_set:casual", config, storage)
    assert config.format.card_style == "casual"


def test_format_toggle_blockquote(config, storage):
    render_menu_for_user("u1", config, storage, "main")
    before = config.format.blockquote_why
    handle_callback("u1", "menu:format:toggle_bq", config, storage)
    assert config.format.blockquote_why == (not before)


def test_format_items_set(config, storage):
    render_menu_for_user("u1", config, storage, "main")
    handle_callback("u1", "menu:format:items_set:7", config, storage)
    assert config.format.items_per_topic == 7


def test_pause_set_and_resume(config, storage):
    render_menu_for_user("u1", config, storage, "main")
    handle_callback("u1", "menu:pause:set:3", config, storage)
    row = storage.fetchone("SELECT current_state FROM bot_state WHERE user_id = %s", ("u1",))
    assert (row.get("current_state") if row else "") == "paused"

    handle_callback("u1", "menu:pause:resume", config, storage)
    row = storage.fetchone("SELECT current_state FROM bot_state WHERE user_id = %s", ("u1",))
    assert (row.get("current_state") if row else "") == "active"


def test_notify_toggle(config, storage):
    render_menu_for_user("u1", config, storage, "main")
    # toggle build_start from default (False) → True
    handle_callback("u1", "menu:notify:toggle:build_start", config, storage)
    from newsbrief.bot.screens.notify import _get_flags
    flags = _get_flags(storage, "u1")
    assert flags["build_start"] is True


def test_reset_confirm_resets(config, storage):
    render_menu_for_user("u1", config, storage, "main")
    config.user.language = "en"
    handle_callback("u1", "menu:reset:confirm", config, storage)
    assert config.user.language == "ru"


def test_unknown_callback_graceful(config, storage):
    view = handle_callback("u1", "menu:does_not_exist:open", config, storage)
    # Falls back to default
    assert "text" in view and "keyboard" in view


def test_bad_callback_format(config, storage):
    view = handle_callback("u1", "fb:1:2:up", config, storage)
    assert "keyboard" in view
    assert view["screen"] == "main"


def test_back_navigation(config, storage):
    view = handle_callback("u1", "menu:main:open", config, storage)
    assert view["screen"] == "main"
