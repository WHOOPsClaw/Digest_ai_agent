"""Statistics screen."""
from __future__ import annotations

from newsbrief.bot.menu import MenuScreen, back_button, register_screen


PERIODS = [("7 дней", 7), ("30 дней", 30)]


def _count(storage, sql, params=()) -> int:
    if storage is None:
        return 0
    try:
        row = storage.fetchone(sql, params)
    except Exception:
        return 0
    if not row:
        return 0
    val = row.get("n") if isinstance(row, dict) else row[0]
    try:
        return int(val or 0)
    except Exception:
        return 0


@register_screen
class StatsScreen(MenuScreen):
    screen_id = "stats"

    def render(self, user_id, config, storage):
        # Default period = 7 days
        return self._render_for(7, storage)

    def handle(self, user_id, action, config, storage, value="", extra=""):
        if action == "period":
            try:
                days = int(value)
            except Exception:
                days = 7
            # Can't easily return alternate render from handle; re-use state:
            # stash in a sub-screen id
            return f"stats_{days}"
        return None

    # Internal
    def _render_for(self, days: int, storage) -> dict:
        digests = _count(
            storage,
            "SELECT COUNT(*) AS n FROM digests "
            f"WHERE created_at >= date('now', '-{days} days')",
        )
        up = _count(
            storage,
            "SELECT COUNT(*) AS n FROM feedback "
            f"WHERE rating='up' AND created_at >= date('now', '-{days} days')",
        )
        down = _count(
            storage,
            "SELECT COUNT(*) AS n FROM feedback "
            f"WHERE rating='down' AND created_at >= date('now', '-{days} days')",
        )
        saves = _count(
            storage,
            "SELECT COUNT(*) AS n FROM feedback "
            f"WHERE rating='save' AND created_at >= date('now', '-{days} days')",
        )
        text = (
            f"📊 <b>Статистика — {days} дней</b>\n\n"
            f"Дайджестов: <b>{digests}</b>\n"
            f"👍: <b>{up}</b>\n"
            f"👎: <b>{down}</b>\n"
            f"📌 сохранено: <b>{saves}</b>"
        )
        rows = []
        for label, d in PERIODS:
            mark = " ✅" if d == days else ""
            rows.append([{
                "text": f"{label}{mark}",
                "callback_data": f"menu:stats:period:{d}",
            }])
        rows.append([back_button()])
        return {"text": text, "keyboard": rows}


@register_screen
class Stats7Screen(StatsScreen):
    screen_id = "stats_7"

    def render(self, user_id, config, storage):
        return self._render_for(7, storage)


@register_screen
class Stats30Screen(StatsScreen):
    screen_id = "stats_30"

    def render(self, user_id, config, storage):
        return self._render_for(30, storage)
