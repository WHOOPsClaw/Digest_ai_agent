"""Profile & interests screen."""
from __future__ import annotations

import logging

from newsbrief.bot.menu import MenuScreen, back_button, register_screen
from newsbrief.bot import fsm

logger = logging.getLogger("newsbrief")

LANG_PRESETS = [
    ("🇷🇺 Русский",  "ru"),
    ("🇬🇧 English",  "en"),
    ("🇪🇸 Español",  "es"),
    ("🇩🇪 Deutsch",  "de"),
]
STYLE_PRESETS = [
    ("Деловой",       "business"),
    ("Академический", "academic"),
    ("Разговорный",   "casual"),
    ("Краткий",       "short"),
    ("Подробный",     "detailed"),
]


@register_screen
class ProfileScreen(MenuScreen):
    screen_id = "profile"

    def render(self, user_id, config, storage):
        lang = "ru"
        profile = ""
        style = "business"
        if config:
            lang = getattr(config.user, "language", "ru")
            profile = getattr(config.user, "profile", "")
            style = getattr(config.format, "card_style", "medium")
        lang_label = next((l for l, v in LANG_PRESETS if v == lang), lang)

        text = (
            "🎯 <b>Интересы и профиль</b>\n\n"
            f"Язык: {lang_label}\n"
            f"Стиль: {style}\n\n"
            "Профиль:\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"{profile or '(пусто)'}\n"
            "━━━━━━━━━━━━━━━━━━"
        )
        keyboard = [
            [{"text": "✏️ Профиль",            "callback_data": "menu:profile:edit"}],
            [{"text": "🌐 Язык",               "callback_data": "menu:profile:lang"}],
            [{"text": "🎭 Стиль",              "callback_data": "menu:profile:style"}],
            [{"text": "🔍 Обновить источники", "callback_data": "menu:profile:refresh"}],
            [back_button()],
        ]
        return {"text": text, "keyboard": keyboard}

    def handle(self, user_id, action, config, storage, value="", extra=""):
        if action == "edit":
            fsm.set_user_state(user_id, "awaiting_profile_text", {}, storage)
            return "profile_edit"
        if action == "lang":
            return "profile_lang"
        if action == "style":
            return "profile_style"
        if action == "lang_set":
            if config:
                config.user.language = value
                try:
                    config.save()
                except Exception as e:
                    logger.warning("[profile] save failed: %s", e)
            return "profile"
        if action == "style_set":
            if config:
                config.format.card_style = value
                try:
                    config.save()
                except Exception as e:
                    logger.warning("[profile] save failed: %s", e)
            return "profile"
        if action == "refresh":
            return "profile"
        return None


@register_screen
class ProfileEditScreen(MenuScreen):
    screen_id = "profile_edit"

    def render(self, user_id, config, storage):
        return {
            "text": (
                "✏️ Пришли новым сообщением описание себя и своих интересов.\n"
                "Например: <i>Разработчик, интересует AI-инфраструктура и стартапы.</i>"
            ),
            "keyboard": [[back_button("profile")]],
        }


@register_screen
class ProfileLangScreen(MenuScreen):
    screen_id = "profile_lang"

    def render(self, user_id, config, storage):
        current = getattr(config.user, "language", "ru") if config else "ru"
        rows = []
        for label, code in LANG_PRESETS:
            marker = " ✅" if code == current else ""
            rows.append([{"text": label + marker, "callback_data": f"menu:profile:lang_set:{code}"}])
        rows.append([back_button("profile")])
        return {"text": "🌐 Язык дайджеста:", "keyboard": rows}


@register_screen
class ProfileStyleScreen(MenuScreen):
    screen_id = "profile_style"

    def render(self, user_id, config, storage):
        current = getattr(config.format, "card_style", "medium") if config else "medium"
        rows = []
        for label, code in STYLE_PRESETS:
            marker = " ✅" if code == current else ""
            rows.append([{"text": label + marker, "callback_data": f"menu:profile:style_set:{code}"}])
        rows.append([back_button("profile")])
        return {"text": "🎭 Стиль изложения:", "keyboard": rows}
