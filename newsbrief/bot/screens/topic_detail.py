"""Topic-detail screen (per-topic sources / interests / limits)."""
from __future__ import annotations

from newsbrief.bot.menu import MenuScreen, back_button, register_screen
from newsbrief.bot import fsm


def _find_topic(config, topic_id: str):
    if not config:
        return None
    for t in getattr(config, "topics", []) or []:
        if t.id == topic_id:
            return t
    return None


def _source_lines(topic) -> list:
    srcs = getattr(topic, "sources", {}) or {}
    lines: list = []
    if isinstance(srcs, dict):
        for kind, val in srcs.items():
            if isinstance(val, list):
                for v in val:
                    lines.append(f"• ✅ {kind}: {v}")
            else:
                lines.append(f"• ✅ {kind}: {val}")
    elif isinstance(srcs, list):
        for v in srcs:
            lines.append(f"• ✅ {v}")
    return lines


@register_screen
class TopicDetailScreen(MenuScreen):
    """Routed under screen_id ``topic``. Expects ``value`` to be the topic id."""

    screen_id = "topic"

    def render(self, user_id, config, storage):
        # Topic id passed via FSM context; default to first topic
        _state, ctx = fsm.get_user_state(user_id, storage)
        topic_id = (ctx or {}).get("topic_id", "")
        topic = _find_topic(config, topic_id)
        if topic is None:
            topics = list(getattr(config, "topics", []) or []) if config else []
            topic = topics[0] if topics else None

        if topic is None:
            return {
                "text": "⚠️ Тема не найдена.",
                "keyboard": [[back_button("sources")]],
            }

        src_lines = _source_lines(topic)
        interests = getattr(topic, "interests_boost", []) or []
        text_lines = [
            f"{topic.emoji} <b>{topic.name}</b>",
            "",
            f"Источники ({len(src_lines)}):",
            *src_lines[:10],
            "",
            f"Интересы: {', '.join(interests) if interests else '—'}",
            f"Карточек в дайджест: {topic.items_per_digest}",
        ]
        keyboard = [
            [{"text": "➕ Источник",  "callback_data": f"menu:topic:addsrc:{topic.id}"}],
            [{"text": "✏️ Интересы",   "callback_data": f"menu:topic:interests:{topic.id}"}],
            [{"text": f"🔢 Лимит ({topic.items_per_digest})",
              "callback_data": f"menu:topic:limit:{topic.id}"}],
            [{"text": "🚫 Удалить тему", "callback_data": f"menu:topic:delete:{topic.id}"}],
            [back_button("sources_list")],
        ]
        return {"text": "\n".join(text_lines), "keyboard": keyboard}

    def handle(self, user_id, action, config, storage, value="", extra=""):
        if action == "open":
            # Store topic_id into FSM context so render() can pick it up
            fsm.set_user_state(user_id, "viewing_topic", {"topic_id": value}, storage)
            return "topic"
        if action == "addsrc":
            fsm.set_user_state(user_id, "awaiting_rss_url", {"topic_id": value}, storage)
            return "topic"
        if action == "interests":
            fsm.set_user_state(user_id, f"awaiting_interests_text:{value}", {"topic_id": value}, storage)
            return "topic"
        if action == "limit":
            fsm.set_user_state(user_id, "awaiting_items_limit", {"topic_id": value}, storage)
            return "topic"
        if action == "delete":
            if config:
                config.topics = [t for t in config.topics if t.id != value]
                try:
                    config.save()
                except Exception:
                    pass
            return "sources_list"
        return None
