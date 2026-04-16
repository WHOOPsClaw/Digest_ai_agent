"""Notifications screen."""
from __future__ import annotations

import json
import logging

from newsbrief.bot.menu import MenuScreen, back_button, register_screen

logger = logging.getLogger("newsbrief")

DEFAULT_FLAGS = {
    "build_start":   False,
    "build_success": True,
    "build_failure": True,
    "daily_summary": True,
    "weekly_stats":  False,
}

FLAG_LABELS = {
    "build_start":   "🔔 Начало сборки",
    "build_success": "✅ Успешная сборка",
    "build_failure": "❌ Ошибка сборки",
    "daily_summary": "📰 Ежедневный дайджест",
    "weekly_stats":  "📊 Недельная статистика",
}


def _get_flags(storage, user_id: str) -> dict:
    if storage is None:
        return dict(DEFAULT_FLAGS)
    try:
        row = storage.fetchone(
            "SELECT context_json FROM bot_state WHERE user_id = %s",
            (f"notify:{user_id}",),
        )
    except Exception:
        return dict(DEFAULT_FLAGS)
    flags = dict(DEFAULT_FLAGS)
    if row:
        raw = row.get("context_json") if isinstance(row, dict) else row[0]
        if raw:
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    flags.update({k: bool(v) for k, v in parsed.items() if k in DEFAULT_FLAGS})
            except Exception:
                pass
    return flags


def _set_flags(storage, user_id: str, flags: dict) -> None:
    if storage is None:
        return
    try:
        storage.execute(
            "INSERT OR REPLACE INTO bot_state (user_id, current_state, context_json, updated_at) "
            "VALUES (%s, %s, %s, CURRENT_TIMESTAMP)",
            (f"notify:{user_id}", "notify_prefs", json.dumps(flags)),
        )
    except Exception as e:
        logger.warning("[notify] save failed: %s", e)


@register_screen
class NotificationsScreen(MenuScreen):
    screen_id = "notify"

    def render(self, user_id, config, storage):
        flags = _get_flags(storage, user_id)
        lines = ["🔔 <b>Уведомления</b>", "", "Нажми, чтобы переключить:"]
        rows = []
        for key, label in FLAG_LABELS.items():
            on = flags.get(key, False)
            mark = "✅" if on else "⬜"
            rows.append([{
                "text": f"{mark} {label}",
                "callback_data": f"menu:notify:toggle:{key}",
            }])
        rows.append([back_button()])
        return {"text": "\n".join(lines), "keyboard": rows}

    def handle(self, user_id, action, config, storage, value="", extra=""):
        if action == "toggle" and value in DEFAULT_FLAGS:
            flags = _get_flags(storage, user_id)
            flags[value] = not flags.get(value, False)
            _set_flags(storage, user_id, flags)
            return "notify"
        return None
