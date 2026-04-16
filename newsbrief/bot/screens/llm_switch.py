"""Switch active LLM provider — list configured providers, click to activate."""
from __future__ import annotations

import logging

from newsbrief.bot.menu import MenuScreen, back_button, register_screen
from newsbrief.llm import manager as llm_manager

logger = logging.getLogger("newsbrief")


@register_screen
class LLMSwitchScreen(MenuScreen):
    screen_id = "llm_switch"

    def render(self, user_id, config, storage):
        if config is None:
            return {"text": "⚠️ Конфиг недоступен.", "keyboard": [[back_button("llm")]]}
        providers = llm_manager.list_providers(config)
        if not providers:
            return {
                "text": "Нет настроенных провайдеров. Добавь хотя бы один.",
                "keyboard": [[back_button("llm")]],
            }
        rows = []
        for p in providers:
            marker = " ✅" if p["active"] else ""
            label = f"{p['display_name']}" + (f" — {p['model']}" if p["model"] else "") + marker
            rows.append([{
                "text": label,
                "callback_data": f"menu:llm_switch:set:{p['id']}",
            }])
        rows.append([back_button("llm")])
        return {"text": "🔄 <b>Переключить провайдера</b>\n\nВыбери активный:", "keyboard": rows}

    def handle(self, user_id, action, config, storage, value="", extra=""):
        if action == "set" and config and value:
            ok = llm_manager.set_active(config, value)
            if ok:
                try:
                    config.save()
                except Exception as e:  # noqa: BLE001
                    logger.warning("[llm_switch] save failed: %s", e)
            return "llm"
        return None
