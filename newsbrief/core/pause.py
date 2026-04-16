"""core/pause.py — pause/resume state for digest delivery.

Stores `paused_until` (ISO timestamp) in the bot_state table under a
well-known user_id key. Scheduler consults `is_paused(storage)` before
sending.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger("newsbrief")

PAUSE_KEY = "__digest_pause__"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(s: str) -> Optional[datetime]:
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def get_paused_until(storage) -> Optional[datetime]:
    """Return paused_until as timezone-aware datetime, or None if not paused."""
    if storage is None:
        return None
    try:
        row = storage.fetchone(
            "SELECT context_json FROM bot_state WHERE user_id = %s",
            (PAUSE_KEY,),
        )
    except Exception as e:
        logger.warning("[pause] lookup failed: %s", e)
        return None
    if not row:
        return None
    ctx_raw = row.get("context_json") if isinstance(row, dict) else None
    if not ctx_raw:
        return None
    try:
        ctx = json.loads(ctx_raw)
    except Exception:
        return None
    until = ctx.get("paused_until")
    if not until:
        return None
    return _parse_iso(until)


def is_paused(storage) -> bool:
    """Return True iff digest is currently paused."""
    until = get_paused_until(storage)
    if until is None:
        return False
    return until > _now()


def pause(storage, days: int = 1) -> datetime:
    """Pause delivery for `days` days. Returns the paused_until datetime."""
    until = _now() + timedelta(days=days)
    ctx = json.dumps({"paused_until": until.isoformat()})
    # Upsert — try insert, fallback to update.
    try:
        existing = storage.fetchone(
            "SELECT user_id FROM bot_state WHERE user_id = %s",
            (PAUSE_KEY,),
        )
    except Exception:
        existing = None
    if existing:
        storage.execute(
            "UPDATE bot_state SET context_json = %s, updated_at = CURRENT_TIMESTAMP "
            "WHERE user_id = %s",
            (ctx, PAUSE_KEY),
        )
    else:
        storage.execute(
            "INSERT INTO bot_state (user_id, current_state, context_json) "
            "VALUES (%s, %s, %s)",
            (PAUSE_KEY, "paused", ctx),
        )
    return until


def resume(storage) -> None:
    """Clear pause state."""
    try:
        storage.execute(
            "DELETE FROM bot_state WHERE user_id = %s",
            (PAUSE_KEY,),
        )
    except Exception as e:
        logger.warning("[pause] resume failed: %s", e)
