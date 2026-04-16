"""bot/fsm.py — Finite state machine for multi-step text input.

Stores state in the ``bot_state`` SQLite table (see core/storage.py).

A "state" is a short string identifier (e.g. ``awaiting_schedule_input``) that
tells the text-message handler how to interpret the next incoming message.
An optional JSON ``context`` carries extra data (e.g. which topic is being
edited).
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

logger = logging.getLogger("newsbrief")


# Canonical state identifiers used across the bot. Handlers may append a suffix
# via ``state:value`` to embed a parameter without creating new rows.
STATES: dict[str, str] = {
    "awaiting_schedule_input": "Waiting for HH:MM for delivery time",
    "awaiting_build_buffer":   "Waiting for build buffer minutes",
    "awaiting_custom_tz":      "Waiting for timezone string",
    "awaiting_llm_key":        "Waiting for LLM API key (suffixed with :preset)",
    "awaiting_llm_add_key":        "Waiting for API key (add-flow, suffixed with :preset_id)",
    "awaiting_llm_add_base_url":   "Waiting for custom provider base_url",
    "awaiting_llm_add_model":      "Waiting for custom provider model name",
    "awaiting_llm_add_name":       "Waiting for display name of new provider",
    "awaiting_profile_text":   "Waiting for profile / bio text",
    "awaiting_interests_text": "Waiting for topic interests (suffixed with :topic_id)",
    "awaiting_rss_url":        "Waiting for RSS URL (suffixed with :topic_id)",
    "awaiting_items_limit":    "Waiting for items-per-digest integer",
    "awaiting_topic_name":     "Waiting for new topic name",
}


def get_user_state(user_id: str, storage) -> tuple[Optional[str], dict]:
    """Return (state, context) for the user, or (None, {}) if not set / paused."""
    if storage is None:
        return None, {}
    try:
        row = storage.fetchone(
            "SELECT current_state, context_json FROM bot_state WHERE user_id = %s",
            (str(user_id),),
        )
    except Exception as e:
        logger.warning("[fsm] get_user_state failed: %s", e)
        return None, {}
    if not row:
        return None, {}
    state = row.get("current_state") if isinstance(row, dict) else row[0]
    raw_ctx = row.get("context_json") if isinstance(row, dict) else (row[1] if len(row) > 1 else None)
    ctx: dict[str, Any] = {}
    if raw_ctx:
        try:
            ctx = json.loads(raw_ctx)
            if not isinstance(ctx, dict):
                ctx = {}
        except Exception:
            ctx = {}
    return state, ctx


def set_user_state(user_id: str, state: str, context: Optional[dict], storage) -> None:
    """Upsert state + context for user."""
    if storage is None:
        return
    payload = json.dumps(context or {}, ensure_ascii=False)
    try:
        storage.execute(
            "INSERT OR REPLACE INTO bot_state (user_id, current_state, context_json, updated_at) "
            "VALUES (%s, %s, %s, CURRENT_TIMESTAMP)",
            (str(user_id), state, payload),
        )
    except Exception as e:
        logger.warning("[fsm] set_user_state failed: %s", e)


def clear_user_state(user_id: str, storage) -> None:
    """Clear FSM state (retain row, but drop current_state)."""
    if storage is None:
        return
    try:
        storage.execute(
            "INSERT OR REPLACE INTO bot_state (user_id, current_state, context_json, updated_at) "
            "VALUES (%s, %s, %s, CURRENT_TIMESTAMP)",
            (str(user_id), "", "{}"),
        )
    except Exception as e:
        logger.warning("[fsm] clear_user_state failed: %s", e)


def is_awaiting(state: Optional[str]) -> bool:
    """True if ``state`` indicates the FSM expects text input."""
    if not state:
        return False
    return state.startswith("awaiting_")
