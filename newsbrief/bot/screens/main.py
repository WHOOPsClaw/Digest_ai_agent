"""Main settings menu."""
from __future__ import annotations

from newsbrief.bot.menu import MenuScreen, register_screen


MAIN_TEXT = (
    "⚙️ <b>Настройки newsbrief</b>\n\n"
    "Что хочешь изменить?"
)

MAIN_ITEMS = [
    ("🕐 Время доставки",       "schedule"),
    ("🤖 LLM провайдер",        "llm"),
    ("📰 Источники и темы",     "sources"),
    ("🎯 Интересы и профиль",   "profile"),
    ("🎨 Формат дайджеста",     "format"),
    ("🔔 Уведомления",          "notify"),
    ("📊 Статистика",           "stats"),
    ("⏸ Пауза / возобновить",  "pause"),
    ("🔧 Диагностика",          "diag"),
    ("❌ Сбросить",             "reset"),
]


@register_screen
class MainMenuScreen(MenuScreen):
    screen_id = "main"

    def render(self, user_id, config, storage):
        keyboard = [
            [{"text": label, "callback_data": f"menu:{target}:open"}]
            for label, target in MAIN_ITEMS
        ]
        return {"text": MAIN_TEXT, "keyboard": keyboard}

    def handle(self, user_id, action, config, storage, value="", extra=""):
        # From main, "open" navigations are handled at dispatcher level.
        return None
