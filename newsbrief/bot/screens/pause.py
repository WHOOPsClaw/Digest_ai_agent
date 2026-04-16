"""Pause / resume screen."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

from newsbrief.bot.menu import MenuScreen, back_button, register_screen

logger = logging.getLogger("newsbrief")

PAUSE_OPTIONS = [
    ("⏸ 1 день",        1),
    ("⏸ 3 дня",         3),
    ("⏸ 7 дней",        7),
    ("⏸ 30 дней",       30),
    ("⏸ До команды",    0),
]


def _get_pause_state(storage, user_id: str) -> dict:
    if storage is None:
        return {}
    try:
        row = storage.fetchone(
            "SELECT current_state, context_json FROM bot_state WHERE user_id = %s",
            (str(user_id),),
        )
    except Exception:
        return {}
    if not row:
        return {}
    raw = row.get("context_json") if isinstance(row, dict) else (row[1] if len(row) > 1 else None)
    state = row.get("current_state") if isinstance(row, dict) else row[0]
    ctx = {}
    if raw:
        try:
            ctx = json.loads(raw) or {}
        except Exception:
            ctx = {}
    ctx["_state"] = state
    return ctx


def _set_paused(storage, user_id: str, days: int) -> None:
    if storage is None:
        return
    if days <= 0:
        until = None
        state = "paused"
    else:
        until = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()
        state = "paused"
    payload = json.dumps({"paused_until": until})
    try:
        storage.execute(
            "INSERT OR REPLACE INTO bot_state (user_id, current_state, context_json, updated_at) "
            "VALUES (%s, %s, %s, CURRENT_TIMESTAMP)",
            (str(user_id), state, payload),
        )
    except Exception as e:
        logger.warning("[pause] save failed: %s", e)


def _resume(storage, user_id: str) -> None:
    if storage is None:
        return
    try:
        storage.execute(
            "INSERT OR REPLACE INTO bot_state (user_id, current_state, context_json, updated_at) "
            "VALUES (%s, %s, %s, CURRENT_TIMESTAMP)",
            (str(user_id), "active", "{}"),
        )
    except Exception as e:
        logger.warning("[pause] resume failed: %s", e)


@register_screen
class PauseScreen(MenuScreen):
    screen_id = "pause"

    def render(self, user_id, config, storage):
        ctx = _get_pause_state(storage, user_id)
        state = ctx.get("_state") or ""
        until = ctx.get("paused_until")
        if state == "paused":
            if until:
                status = f"⏸ На паузе до <b>{until[:16].replace('T', ' ')}</b>"
            else:
                status = "⏸ На паузе (до команды)"
        else:
            status = "▶️ Активно"

        text = "⏸ <b>Пауза / возобновление</b>\n\n" + status
        rows = [[{"text": label, "callback_data": f"menu:pause:set:{days}"}]
                for label, days in PAUSE_OPTIONS]
        rows.append([{"text": "▶️ Возобновить", "callback_data": "menu:pause:resume"}])
        rows.append([back_button()])
        return {"text": text, "keyboard": rows}

    def handle(self, user_id, action, config, storage, value="", extra=""):
        if action == "set":
            try:
                days = int(value)
            except Exception:
                days = 0
            _set_paused(storage, user_id, days)
            return "pause"
        if action == "resume":
            _resume(storage, user_id)
            return "pause"
        return None
