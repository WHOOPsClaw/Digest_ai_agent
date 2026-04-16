"""Digest format screen."""
from __future__ import annotations

import logging

from newsbrief.bot.menu import MenuScreen, back_button, register_screen

logger = logging.getLogger("newsbrief")

LENGTH_PRESETS = [
    ("Короткий",  "short"),
    ("Средний",   "medium"),
    ("Детальный", "detailed"),
]


@register_screen
class FormatScreen(MenuScreen):
    screen_id = "format"

    def render(self, user_id, config, storage):
        items = getattr(config.format, "items_per_topic", 5) if config else 5
        style = getattr(config.format, "card_style", "medium") if config else "medium"
        blockq = getattr(config.format, "blockquote_why", True) if config else True
        bq_str = "✅ включена" if blockq else "❌ выключена"

        text = (
            "🎨 <b>Формат дайджеста</b>\n\n"
            f"Карточек на тему: <b>{items}</b>\n"
            f"Длина: <b>{style}</b>\n"
            f"Цитата «Почему важно»: {bq_str}"
        )
        keyboard = [
            [{"text": f"🔢 Кол-во ({items})", "callback_data": "menu:format:items"}],
            [{"text": "📏 Длина",              "callback_data": "menu:format:length"}],
            [{"text": "💬 Блок «Почему важно»", "callback_data": "menu:format:toggle_bq"}],
            [back_button()],
        ]
        return {"text": text, "keyboard": keyboard}

    def handle(self, user_id, action, config, storage, value="", extra=""):
        if action == "items":
            return "format_items"
        if action == "length":
            return "format_length"
        if action == "toggle_bq":
            if config:
                config.format.blockquote_why = not getattr(config.format, "blockquote_why", True)
                try:
                    config.save()
                except Exception as e:
                    logger.warning("[format] save failed: %s", e)
            return "format"
        if action == "items_set":
            if config:
                try:
                    config.format.items_per_topic = max(1, min(20, int(value)))
                    config.save()
                except Exception as e:
                    logger.warning("[format] save failed: %s", e)
            return "format"
        if action == "length_set":
            if config:
                config.format.card_style = value
                try:
                    config.save()
                except Exception as e:
                    logger.warning("[format] save failed: %s", e)
            return "format"
        return None


@register_screen
class FormatItemsScreen(MenuScreen):
    screen_id = "format_items"

    def render(self, user_id, config, storage):
        rows = []
        for n in (3, 5, 7, 10):
            rows.append([{"text": f"{n} карточек", "callback_data": f"menu:format:items_set:{n}"}])
        rows.append([back_button("format")])
        return {"text": "🔢 Сколько карточек на тему?", "keyboard": rows}


@register_screen
class FormatLengthScreen(MenuScreen):
    screen_id = "format_length"

    def render(self, user_id, config, storage):
        current = getattr(config.format, "card_style", "medium") if config else "medium"
        rows = []
        for label, code in LENGTH_PRESETS:
            marker = " ✅" if code == current else ""
            rows.append([{"text": label + marker, "callback_data": f"menu:format:length_set:{code}"}])
        rows.append([back_button("format")])
        return {"text": "📏 Длина карточек:", "keyboard": rows}
