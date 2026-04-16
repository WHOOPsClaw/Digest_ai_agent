"""feedback/health_monitor.py — detect dead / stale sources.

A source is "dead" if fewer than MIN_ITEMS_HEALTHY articles landed in the
articles table over the last `days` days.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger("newsbrief")

MIN_ITEMS_HEALTHY = 3
DEFAULT_WINDOW_DAYS = 14


def _source_key(source_ref: dict) -> str:
    """Produce a match key for a source. Prefer explicit `source` string, then url/id."""
    return (
        source_ref.get("source")
        or source_ref.get("id")
        or source_ref.get("url")
        or source_ref.get("name")
        or ""
    )


def check_source_health(
    source_ref: dict,
    storage: Any,
    days: int = DEFAULT_WINDOW_DAYS,
) -> dict:
    """Check a single source. Returns health record."""
    key = _source_key(source_ref)
    result = {
        "source":      key,
        "healthy":     True,
        "last_item":   None,
        "items_count": 0,
        "reason":      "",
    }
    if not key or storage is None:
        result["healthy"] = False
        result["reason"] = "no source key / no storage"
        return result

    try:
        d = int(days)
        if getattr(storage, "is_postgres", False):
            sql = (
                "SELECT COUNT(*) AS n, MAX(fetched_at) AS last FROM articles "
                f"WHERE source = %s AND fetched_at >= NOW() - INTERVAL '{d} days'"
            )
        else:
            sql = (
                "SELECT COUNT(*) AS n, MAX(fetched_at) AS last FROM articles "
                f"WHERE source = %s AND fetched_at >= datetime('now', '-{d} days')"
            )
        row = storage.fetchone(sql, (key,)) or {}
    except Exception as e:
        logger.warning("[health_monitor] query failed for %s: %s", key, e)
        result["healthy"] = False
        result["reason"] = f"query error: {e}"
        return result

    n = int(row.get("n") or 0) if isinstance(row, dict) else int((row or [0])[0] or 0)
    last = row.get("last") if isinstance(row, dict) else None
    result["items_count"] = n
    result["last_item"] = last
    if n < MIN_ITEMS_HEALTHY:
        result["healthy"] = False
        result["reason"] = f"only {n} items in {days}d (min={MIN_ITEMS_HEALTHY})"
    return result


def _iter_sources(config: Any):
    """Flatten source references from all topics of a config."""
    for topic in getattr(config, "topics", []) or []:
        sources = getattr(topic, "sources", {}) or {}
        if isinstance(sources, dict):
            for stype, entries in sources.items():
                if isinstance(entries, list):
                    for entry in entries:
                        if isinstance(entry, dict):
                            yield {"source": entry.get("id") or entry.get("url") or stype, **entry}
                        else:
                            yield {"source": str(entry)}
                elif isinstance(entries, dict):
                    yield {"source": stype, **entries}


def monitor_all_sources(config: Any, storage: Any, days: int = DEFAULT_WINDOW_DAYS) -> list[dict]:
    """Check every source in config. Return list of unhealthy health records."""
    unhealthy: list[dict] = []
    for ref in _iter_sources(config):
        rec = check_source_health(ref, storage, days=days)
        if not rec["healthy"]:
            unhealthy.append(rec)
    logger.info("[health_monitor] unhealthy sources: %d", len(unhealthy))
    return unhealthy


def notify_dead_sources(unhealthy: list[dict], telegram_channel: Any) -> None:
    """Send a Telegram alert listing dead sources."""
    if not unhealthy or telegram_channel is None:
        return
    lines = ["⚠️ <b>Dead sources detected</b>", ""]
    for rec in unhealthy[:20]:
        lines.append(f"• {rec.get('source','?')} — {rec.get('reason','')}")
    text = "\n".join(lines)
    try:
        if hasattr(telegram_channel, "send_message"):
            telegram_channel.send_message(text)
        elif hasattr(telegram_channel, "send"):
            telegram_channel.send(text)
        elif hasattr(telegram_channel, "send_digest"):
            telegram_channel.send_digest([text], digest_id=0)
    except Exception as e:
        logger.warning("[health_monitor] notify failed: %s", e)
