"""Diagnostics screen."""
from __future__ import annotations

from newsbrief.bot.menu import MenuScreen, back_button, register_screen


def _doctor_summary(config) -> str:
    try:
        from newsbrief.core.doctor import run_doctor  # type: ignore
        report = run_doctor(config)
        if isinstance(report, dict):
            parts = []
            for k, v in report.items():
                parts.append(f"• <b>{k}</b>: {v}")
            return "\n".join(parts[:20])
        return str(report)[:1500]
    except Exception as e:
        return f"(doctor недоступен: {e})"


def _last_pipeline(storage) -> str:
    if storage is None:
        return "—"
    try:
        row = storage.fetchone(
            "SELECT status, duration_sec, item_count, started_at "
            "FROM pipeline_runs ORDER BY started_at DESC LIMIT 1"
        )
    except Exception:
        return "—"
    if not row:
        return "—"
    if isinstance(row, dict):
        return (
            f"{row.get('status', '?')}, "
            f"{round(float(row.get('duration_sec') or 0), 1)} сек, "
            f"{row.get('item_count', 0)} ст., "
            f"{row.get('started_at', '')}"
        )
    return str(row)


@register_screen
class DiagnosticsScreen(MenuScreen):
    screen_id = "diag"

    def render(self, user_id, config, storage):
        text = (
            "🔧 <b>Диагностика</b>\n\n"
            + _doctor_summary(config)
            + "\n\nПоследняя сборка: "
            + _last_pipeline(storage)
        )
        keyboard = [
            [{"text": "🧪 Прогнать тест",       "callback_data": "menu:diag:run_test"}],
            [{"text": "🔄 Пересобрать сейчас",  "callback_data": "menu:diag:rebuild"}],
            [{"text": "📜 Логи",                "callback_data": "menu:diag:logs"}],
            [back_button()],
        ]
        return {"text": text, "keyboard": keyboard}

    def handle(self, user_id, action, config, storage, value="", extra=""):
        if action in ("run_test", "rebuild", "logs"):
            # Acknowledge only — actual trigger is wired from the bot runner.
            return "diag"
        return None
