"""Schedule (delivery time) screen."""
from __future__ import annotations

import logging
from typing import Optional

from newsbrief.bot.menu import MenuScreen, back_button, register_screen
from newsbrief.bot import fsm

logger = logging.getLogger("newsbrief")

TIME_PRESETS = ["07:00", "08:00", "09:00", "10:00", "12:00", "18:00", "20:00", "22:00"]
TZ_PRESETS = [
    ("🇷🇺 Moscow",    "Europe/Moscow"),
    ("🇬🇧 London",    "Europe/London"),
    ("🇺🇸 New York",  "America/New_York"),
    ("🇩🇪 Berlin",    "Europe/Berlin"),
    ("🇯🇵 Tokyo",     "Asia/Tokyo"),
    ("🇺🇦 Kyiv",      "Europe/Kyiv"),
]


def _pipeline_stats(storage) -> dict:
    """Return {today_min, avg7_min} from ``pipeline_runs`` (best-effort)."""
    if storage is None:
        return {"today_min": None, "avg7_min": None}
    try:
        today = storage.fetchone(
            "SELECT AVG(duration_sec) AS d FROM pipeline_runs "
            "WHERE run_date = date('now')"
        )
        week = storage.fetchone(
            "SELECT AVG(duration_sec) AS d FROM pipeline_runs "
            "WHERE run_date >= date('now', '-7 days')"
        )
    except Exception:
        return {"today_min": None, "avg7_min": None}

    def _to_min(row):
        if not row:
            return None
        val = row.get("d") if isinstance(row, dict) else row[0]
        if val is None:
            return None
        try:
            return round(float(val) / 60.0, 1)
        except Exception:
            return None

    return {"today_min": _to_min(today), "avg7_min": _to_min(week)}


def _compute_build_at(send_at: str, buffer_min: int) -> str:
    """Subtract ``buffer_min`` from ``send_at`` (HH:MM). Wraps at midnight."""
    try:
        hh, mm = send_at.split(":")
        total = (int(hh) * 60 + int(mm) - buffer_min) % (24 * 60)
        return f"{total // 60:02d}:{total % 60:02d}"
    except Exception:
        return send_at


@register_screen
class ScheduleScreen(MenuScreen):
    screen_id = "schedule"

    def render(self, user_id, config, storage):
        send_at = getattr(config.schedule, "send_at", "09:00") if config else "09:00"
        tz      = getattr(config.schedule, "timezone", "Europe/Moscow") if config else "Europe/Moscow"
        buffer_min = getattr(config.schedule, "build_buffer_minutes", None) if config else None
        if not buffer_min:
            buffer_min = 20
        build_at = getattr(config.schedule, "build_at", None) or _compute_build_at(send_at, buffer_min)
        preset = getattr(config.llm, "preset", "groq") if config else "groq"

        stats = _pipeline_stats(storage)
        today_str = f"{stats['today_min']} мин" if stats["today_min"] is not None else "—"
        avg_str   = f"{stats['avg7_min']} мин" if stats["avg7_min"] is not None else "—"

        text = (
            "🕐 <b>Время доставки</b>\n\n"
            f"Сейчас: дайджест приходит в <b>{send_at}</b> ({tz})\n"
            f"Сборка начинается в <b>{build_at}</b> ({buffer_min} мин запас для {preset})\n\n"
            "Последние сборки:\n"
            f"• сегодня: {today_str}\n"
            f"• avg 7 дней: {avg_str}"
        )
        keyboard = [
            [{"text": "⏰ Изменить время", "callback_data": "menu:schedule:pick_time"}],
            [{"text": "🌍 Часовой пояс",    "callback_data": "menu:schedule:pick_tz"}],
            [back_button()],
        ]
        return {"text": text, "keyboard": keyboard}

    def handle(self, user_id, action, config, storage, value="", extra=""):
        if action == "pick_time":
            return "schedule_pick"
        if action == "preset":
            # value like "09" — reconstruct HH:MM using extra as MM
            hhmm = f"{value}:{extra}" if extra else value
            self._apply_time(config, hhmm)
            return "schedule"
        if action == "custom":
            fsm.set_user_state(user_id, "awaiting_schedule_input", {}, storage)
            return "schedule_await"
        if action == "pick_tz":
            return "schedule_tz"
        if action == "tz_set":
            self._apply_tz(config, value + (":" + extra if extra else ""))
            return "schedule"
        return None

    # --- helpers ------------------------------------------------------

    def _apply_time(self, config, hhmm: str) -> None:
        if not config:
            return
        config.schedule.send_at = hhmm
        buffer_min = config.schedule.build_buffer_minutes or 20
        config.schedule.build_at = _compute_build_at(hhmm, buffer_min)
        try:
            config.save()
        except Exception as e:
            logger.warning("[schedule] save failed: %s", e)

    def _apply_tz(self, config, tz: str) -> None:
        if not config or not tz:
            return
        config.schedule.timezone = tz
        try:
            config.save()
        except Exception as e:
            logger.warning("[schedule] tz save failed: %s", e)


# -- Time-picker sub-screen ---------------------------------------------------

@register_screen
class SchedulePickTimeScreen(MenuScreen):
    """Shown when the user taps 'Изменить время'. Implemented as a sibling screen
    so callback routing stays flat.
    """

    screen_id = "schedule_pick"

    def render(self, user_id, config, storage):
        rows = []
        # 2 per row
        for i in range(0, len(TIME_PRESETS), 2):
            row = []
            for t in TIME_PRESETS[i : i + 2]:
                hh, mm = t.split(":")
                row.append({"text": t, "callback_data": f"menu:schedule:preset:{hh}:{mm}"})
            rows.append(row)
        rows.append([{"text": "✏️ Ввести вручную", "callback_data": "menu:schedule:custom"}])
        rows.append([back_button("schedule")])
        return {
            "text": "⏰ Выбери время доставки (локальное время):",
            "keyboard": rows,
        }


@register_screen
class ScheduleTZScreen(MenuScreen):
    screen_id = "schedule_tz"

    def render(self, user_id, config, storage):
        current = getattr(config.schedule, "timezone", "Europe/Moscow") if config else "Europe/Moscow"
        rows = []
        for label, tz in TZ_PRESETS:
            marker = " ✅" if tz == current else ""
            # tz contains a colon → split into value/extra pieces for callback
            if "/" in tz:
                value = tz  # e.g. Europe/Moscow fits under 64 bytes
            else:
                value = tz
            rows.append([{
                "text": label + marker,
                "callback_data": f"menu:schedule:tz_set:{value}",
            }])
        rows.append([back_button("schedule")])
        return {
            "text": f"🌍 Часовой пояс (сейчас: <b>{current}</b>):",
            "keyboard": rows,
        }


@register_screen
class ScheduleAwaitScreen(MenuScreen):
    """Shown after the user taps 'ввести вручную' — prompts a text reply."""

    screen_id = "schedule_await"

    def render(self, user_id, config, storage):
        text = (
            "✏️ Отправь сообщением новое время в формате <code>HH:MM</code>\n"
            "Например: <code>09:30</code>"
        )
        return {
            "text": text,
            "keyboard": [[back_button("schedule")]],
        }
