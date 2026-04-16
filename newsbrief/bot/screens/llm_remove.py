"""Remove-provider screen with confirm step."""
from __future__ import annotations

import logging

from newsbrief.bot import fsm
from newsbrief.bot.menu import MenuScreen, back_button, register_screen
from newsbrief.llm import manager as llm_manager

logger = logging.getLogger("newsbrief")


@register_screen
class LLMRemoveScreen(MenuScreen):
    screen_id = "llm_remove"

    def render(self, user_id, config, storage):
        if config is None:
            return {"text": "⚠️ Конфиг недоступен.", "keyboard": [[back_button("llm")]]}
        providers = llm_manager.list_providers(config)
        if not providers:
            return {
                "text": "Нет провайдеров для удаления.",
                "keyboard": [[back_button("llm")]],
            }
        rows = []
        for p in providers:
            marker = " (активный)" if p["active"] else ""
            rows.append([{
                "text": f"🗑 {p['display_name']}{marker}",
                "callback_data": f"menu:llm_remove:ask:{p['id']}",
            }])
        rows.append([back_button("llm")])
        return {"text": "🗑 <b>Удалить провайдер</b>\n\nВыбери:", "keyboard": rows}

    def handle(self, user_id, action, config, storage, value="", extra=""):
        if action == "ask" and value:
            fsm.set_user_state(user_id, "confirm_llm_remove", {"provider_id": value}, storage)
            return "llm_remove_confirm"
        if action == "confirm" and config and value:
            ok = llm_manager.remove_provider(config, value)
            if ok:
                try:
                    config.save()
                except Exception as e:  # noqa: BLE001
                    logger.warning("[llm_remove] save failed: %s", e)
            fsm.clear_user_state(user_id, storage)
            return "llm"
        return None


@register_screen
class LLMRemoveConfirmScreen(MenuScreen):
    screen_id = "llm_remove_confirm"

    def render(self, user_id, config, storage):
        _state, ctx = fsm.get_user_state(user_id, storage)
        provider_id = (ctx or {}).get("provider_id") or ""
        text = f"⚠️ Точно удалить провайдер <b>{provider_id}</b>?"
        rows = [
            [{"text": "✅ Да, удалить",
              "callback_data": f"menu:llm_remove:confirm:{provider_id}"}],
            [{"text": "❌ Отмена",
              "callback_data": "menu:llm_remove:open"}],
        ]
        return {"text": text, "keyboard": rows}
