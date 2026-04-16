"""Reset / wipe-config confirmation screen."""
from __future__ import annotations

import logging

from newsbrief.bot.menu import MenuScreen, back_button, register_screen

logger = logging.getLogger("newsbrief")


@register_screen
class ResetScreen(MenuScreen):
    screen_id = "reset"

    def render(self, user_id, config, storage):
        text = (
            "❌ <b>Сброс настроек</b>\n\n"
            "Это удалит все темы, источники, ключи и настройки и вернёт "
            "дефолты. История дайджестов и фидбек останутся.\n\n"
            "Уверен?"
        )
        keyboard = [
            [{"text": "🔴 ДА, сбросить", "callback_data": "menu:reset:confirm"}],
            [{"text": "⬅️ Отмена",       "callback_data": "menu:main:open"}],
        ]
        return {"text": text, "keyboard": keyboard}

    def handle(self, user_id, action, config, storage, value="", extra=""):
        if action == "confirm":
            if config is not None:
                try:
                    from newsbrief.config import NewsbriefConfig
                    fresh = NewsbriefConfig()
                    # Copy fresh values into live config to preserve references
                    for field_name in fresh.model_fields.keys():
                        setattr(config, field_name, getattr(fresh, field_name))
                    config.save()
                except Exception as e:
                    logger.warning("[reset] failed: %s", e)
            return "main"
        return None
