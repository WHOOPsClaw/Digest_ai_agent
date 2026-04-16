"""Sources & topics overview screen."""
from __future__ import annotations

from newsbrief.bot.menu import MenuScreen, back_button, register_screen
from newsbrief.bot import fsm


def _count_sources(topic) -> int:
    srcs = getattr(topic, "sources", {}) or {}
    if isinstance(srcs, dict):
        total = 0
        for v in srcs.values():
            if isinstance(v, list):
                total += len(v)
            elif v:
                total += 1
        return total
    if isinstance(srcs, list):
        return len(srcs)
    return 0


@register_screen
class SourcesScreen(MenuScreen):
    screen_id = "sources"

    def render(self, user_id, config, storage):
        topics = list(getattr(config, "topics", []) or []) if config else []
        n_topics = len(topics)

        lines = [f"📰 <b>Источники и темы</b>\n\nАктивных тем: <b>{n_topics}</b>"]
        total_srcs = 0
        for t in topics[:10]:
            cnt = _count_sources(t)
            total_srcs += cnt
            lines.append(f"• {t.emoji} {t.name} ({cnt} источников, лимит {t.items_per_digest})")
        if n_topics > 10:
            lines.append(f"… и ещё {n_topics - 10}")
        lines.append(f"\nВсего источников: <b>{total_srcs}</b>")

        keyboard = [
            [{"text": "📑 Список тем",      "callback_data": "menu:sources:list"}],
            [{"text": "➕ Добавить тему",   "callback_data": "menu:sources:add"}],
            [{"text": "🔍 Найти новые",     "callback_data": "menu:sources:discover"}],
            [{"text": "✅ Проверить работу", "callback_data": "menu:sources:check"}],
            [back_button()],
        ]
        return {"text": "\n".join(lines), "keyboard": keyboard}

    def handle(self, user_id, action, config, storage, value="", extra=""):
        if action == "list":
            return "sources_list"
        if action == "add":
            fsm.set_user_state(user_id, "awaiting_topic_name", {}, storage)
            return "sources_add"
        if action == "discover":
            return "sources_discover"
        if action == "check":
            return "sources_check"
        return None


@register_screen
class SourcesListScreen(MenuScreen):
    screen_id = "sources_list"

    def render(self, user_id, config, storage):
        topics = list(getattr(config, "topics", []) or []) if config else []
        rows = []
        for t in topics[:20]:
            rows.append([{
                "text": f"{t.emoji} {t.name}",
                "callback_data": f"menu:topic:open:{t.id}",
            }])
        rows.append([{"text": "➕ Добавить тему", "callback_data": "menu:sources:add"}])
        rows.append([back_button("sources")])
        return {
            "text": "📑 <b>Темы</b>\nВыбери тему для настройки:",
            "keyboard": rows,
        }


@register_screen
class SourcesAddScreen(MenuScreen):
    screen_id = "sources_add"

    def render(self, user_id, config, storage):
        return {
            "text": (
                "➕ <b>Новая тема</b>\n\n"
                "Пришли название темы следующим сообщением (например: "
                "<code>Финтех</code>)."
            ),
            "keyboard": [[back_button("sources")]],
        }


@register_screen
class SourcesDiscoverScreen(MenuScreen):
    screen_id = "sources_discover"

    def render(self, user_id, config, storage):
        return {
            "text": (
                "🔍 <b>Поиск источников</b>\n\n"
                "Запусти команду <code>newsbrief discover</code> в терминале — "
                "она предложит RSS по темам в конфиге."
            ),
            "keyboard": [[back_button("sources")]],
        }


@register_screen
class SourcesCheckScreen(MenuScreen):
    screen_id = "sources_check"

    def render(self, user_id, config, storage):
        # Summarise last pipeline run
        summary = "Нет данных."
        try:
            row = storage.fetchone(
                "SELECT status, item_count, duration_sec FROM pipeline_runs "
                "ORDER BY started_at DESC LIMIT 1"
            ) if storage else None
            if row:
                status = row.get("status") if isinstance(row, dict) else row[0]
                items  = row.get("item_count") if isinstance(row, dict) else row[1]
                dur    = row.get("duration_sec") if isinstance(row, dict) else row[2]
                summary = f"Статус: <b>{status}</b>, {items} статей, {round(float(dur or 0), 1)} сек"
        except Exception as e:
            summary = f"⚠️ {e}"
        return {
            "text": "✅ <b>Проверка источников</b>\n\n" + summary,
            "keyboard": [[back_button("sources")]],
        }
