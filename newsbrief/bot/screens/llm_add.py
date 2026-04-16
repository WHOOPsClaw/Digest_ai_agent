"""Add-provider FSM flow.

Step 1: pick preset (or 'custom').
Step 2: enter API key.
(For custom: base_url, then model, then display name.)
On completion: persist via ``manager.add_provider``.
"""
from __future__ import annotations

import logging

from newsbrief.bot import fsm
from newsbrief.bot.menu import MenuScreen, back_button, register_screen
from newsbrief.bot.screens.llm import LLM_PRESETS, _preset_by_id
from newsbrief.llm import manager as llm_manager

logger = logging.getLogger("newsbrief")


@register_screen
class LLMAddScreen(MenuScreen):
    screen_id = "llm_add"

    def render(self, user_id, config, storage):
        rows = [[{"text": "── Пресеты ──", "callback_data": "menu:llm_add:noop"}]]
        for pid, label, _tier, _url in LLM_PRESETS:
            if pid == "custom":
                continue
            rows.append([{"text": label, "callback_data": f"menu:llm_add:pick:{pid}"}])
        rows.append([{"text": "⚙️ Custom (OpenAI-compatible)", "callback_data": "menu:llm_add:pick:custom"}])
        rows.append([back_button("llm")])
        return {
            "text": "➕ <b>Добавить провайдер</b>\n\nВыбери пресет или укажи custom:",
            "keyboard": rows,
        }

    def handle(self, user_id, action, config, storage, value="", extra=""):
        if action == "pick" and value:
            preset_id = value
            if preset_id == "custom":
                fsm.set_user_state(
                    user_id, "awaiting_llm_add_base_url", {"preset": "custom"}, storage,
                )
                return "llm_add_custom"
            # Standard preset → ask for API key.
            fsm.set_user_state(
                user_id, f"awaiting_llm_add_key:{preset_id}",
                {"preset": preset_id}, storage,
            )
            return "llm_add_key"
        return None


@register_screen
class LLMAddKeyScreen(MenuScreen):
    """Prompt for API key after preset selected."""
    screen_id = "llm_add_key"

    def render(self, user_id, config, storage):
        state, ctx = fsm.get_user_state(user_id, storage)
        preset = (ctx or {}).get("preset") or ""
        row = _preset_by_id(preset) if preset else None
        if row:
            _id, label, _tier, url = row
            text = (
                f"🔑 <b>{label}</b>\n\n"
                f"1. Получи API key: <a href=\"{url}\">{url}</a>\n"
                "2. Пришли его следующим сообщением (строкой).\n\n"
                "Ключ хранится локально и не публикуется."
            )
        else:
            text = "🔑 Пришли API key следующим сообщением."
        return {"text": text, "keyboard": [[back_button("llm")]]}


@register_screen
class LLMAddCustomScreen(MenuScreen):
    """Placeholder screen shown while custom-provider FSM collects base_url/model/name."""
    screen_id = "llm_add_custom"

    def render(self, user_id, config, storage):
        state, _ctx = fsm.get_user_state(user_id, storage)
        if state == "awaiting_llm_add_base_url":
            text = (
                "⚙️ <b>Custom provider</b>\n\n"
                "Пришли base_url (например <code>https://api.example.com/v1</code>)."
            )
        elif state == "awaiting_llm_add_model":
            text = "Пришли название модели (например <code>gpt-4o-mini</code>)."
        elif state and state.startswith("awaiting_llm_add_key:"):
            text = "🔑 Пришли API key следующим сообщением."
        elif state == "awaiting_llm_add_name":
            text = "Пришли отображаемое имя провайдера (например <code>Mac Studio</code>)."
        else:
            text = "Провайдер добавлен."
        return {"text": text, "keyboard": [[back_button("llm")]]}


def finalize_add_provider(
    user_id: str,
    config,
    storage,
    *,
    preset_id: str,
    api_key: str,
    base_url: str | None = None,
    model: str | None = None,
    display_name: str | None = None,
) -> str:
    """Persist a new provider from FSM-collected values. Returns the chosen id."""
    from newsbrief.config import SingleLLMConfig

    # Derive unique id: prefer preset name, else 'custom_N'.
    base_id = preset_id if preset_id != "custom" else "custom"
    if config is not None:
        existing = set((config.llm.providers or {}).keys())
        pid = base_id
        n = 2
        while pid in existing:
            pid = f"{base_id}_{n}"
            n += 1
    else:
        pid = base_id

    spec = SingleLLMConfig(
        preset=None if preset_id == "custom" else preset_id,
        provider="openai_compatible" if preset_id == "custom" else None,
        base_url=base_url,
        api_key=api_key,
        model=model,
        display_name=display_name or (preset_id.title() if preset_id != "custom" else "Custom"),
    )

    if config is not None:
        llm_manager.add_provider(config, pid, spec)
        try:
            config.save()
        except Exception as e:  # noqa: BLE001
            logger.warning("[llm_add] save failed: %s", e)
    fsm.clear_user_state(user_id, storage)
    return pid
