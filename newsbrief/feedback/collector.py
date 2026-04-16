"""feedback/collector.py — record feedback and compute aggregate stats.

Thin layer on top of the `feedback` table in storage.
Ratings recorded from the Telegram bot are one of:
    "up", "down", "mute" (→ "blocked"), "save" (→ "saved").

This module exposes a normalized view where:
    up       → positive signal
    down     → negative signal
    blocked  → strong negative (user muted topic/source)
    saved    → strong positive (user saved card)
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("newsbrief")


# Map raw rating strings to normalized bucket names used in stats.
_RATING_ALIASES = {
    "up":      "up",
    "down":    "down",
    "mute":    "blocked",
    "blocked": "blocked",
    "save":    "saved",
    "saved":   "saved",
}


def _normalize(rating: str) -> str:
    return _RATING_ALIASES.get((rating or "").lower(), (rating or "").lower())


def record_feedback(
    storage: Any,
    digest_id: int,
    article_idx: int,
    action: str,
    user_id: str,
    source: str = "",
) -> None:
    """Record a feedback row. Keeps the raw action string intact."""
    if storage is None:
        return
    try:
        storage.execute(
            "INSERT INTO feedback (digest_id, article_url, source, rating, user_id) "
            "VALUES (%s, %s, %s, %s, %s)",
            (digest_id, f"idx:{article_idx}", source, action, user_id),
        )
    except Exception as e:
        logger.warning("[feedback] record failed: %s", e)


def _fetch_rows(storage: Any, days: int) -> list[dict]:
    if storage is None:
        return []
    try:
        sql = (
            "SELECT source, rating FROM feedback "
            "WHERE created_at >= datetime('now', '-%d days')" % int(days)
            if not getattr(storage, "is_postgres", False)
            else "SELECT source, rating FROM feedback "
                 "WHERE created_at >= NOW() - INTERVAL '%d days'" % int(days)
        )
        return storage.fetchall(sql)
    except Exception as e:
        logger.warning("[feedback] fetch failed: %s", e)
        return []


def _score(counts: dict) -> float:
    """score ∈ [-1, +1]: (up + saved - down - 2*blocked) / total. 0 when empty."""
    up      = counts.get("up", 0)
    down    = counts.get("down", 0)
    blocked = counts.get("blocked", 0)
    saved   = counts.get("saved", 0)
    total   = up + down + blocked + saved
    if total == 0:
        return 0.0
    raw = (up + saved - down - 2 * blocked) / total
    # clamp to [-1, +1]
    return max(-1.0, min(1.0, raw))


def get_feedback_stats(storage: Any, days: int = 30) -> dict:
    """Aggregate feedback by source over the last N days.

    Returns:
        {
          "source_ratings": {src: {up, down, blocked, saved, total, score}},
          "top_sources":    [src, ...]  # score DESC
          "bottom_sources": [src, ...]  # score ASC
        }
    """
    rows = _fetch_rows(storage, days)
    by_src: dict[str, dict] = {}
    for row in rows:
        src = (row.get("source") or "").strip() or "unknown"
        rating = _normalize(row.get("rating") or "")
        bucket = by_src.setdefault(
            src, {"up": 0, "down": 0, "blocked": 0, "saved": 0, "total": 0, "score": 0.0}
        )
        if rating in ("up", "down", "blocked", "saved"):
            bucket[rating] += 1
            bucket["total"] += 1

    for src, bucket in by_src.items():
        bucket["score"] = round(_score(bucket), 4)

    ranked = sorted(by_src.items(), key=lambda kv: kv[1]["score"], reverse=True)
    top    = [src for src, b in ranked if b["total"] >= 1 and b["score"] > 0]
    bottom = [src for src, b in reversed(ranked) if b["total"] >= 1 and b["score"] < 0]

    return {
        "source_ratings": by_src,
        "top_sources":    top,
        "bottom_sources": bottom,
    }


def get_source_score(storage: Any, source: str, days: int = 30) -> float:
    """score in [-1, +1] for a single source. Returns 0.0 if no data."""
    stats = get_feedback_stats(storage, days=days)
    bucket = stats["source_ratings"].get(source)
    if not bucket or bucket.get("total", 0) == 0:
        return 0.0
    return float(bucket["score"])


# ---------------------------------------------------------------------------
# New spec API (block/save naming — reporting view)
# ---------------------------------------------------------------------------

def _simple_score(up: int, down: int, block: int, total: int) -> float:
    return (up - down - 2 * block) / max(total, 1)


def get_source_ratings(storage: Any, days: int = 30) -> dict:
    """Aggregate feedback by source, returning the spec-shaped view.

    Returns a dict sorted by score desc:
        {source: {up, down, block, save, total, score}}
    """
    rows = _fetch_rows(storage, days)
    by_src: dict[str, dict] = {}
    for row in rows:
        src = (row.get("source") or "").strip() or "unknown"
        rating = _normalize(row.get("rating") or "")
        # Map normalized "blocked" → "block", "saved" → "save" for the spec view
        key = {"blocked": "block", "saved": "save"}.get(rating, rating)
        if key not in ("up", "down", "block", "save"):
            continue
        bucket = by_src.setdefault(
            src, {"up": 0, "down": 0, "block": 0, "save": 0, "total": 0, "score": 0.0}
        )
        bucket[key] += 1
        bucket["total"] += 1

    for bucket in by_src.values():
        bucket["score"] = round(
            _simple_score(bucket["up"], bucket["down"], bucket["block"], bucket["total"]),
            4,
        )

    return dict(sorted(by_src.items(), key=lambda kv: kv[1]["score"], reverse=True))


def get_top_sources(storage: Any, days: int = 30, min_feedback: int = 5) -> list[dict]:
    """Sources with enough feedback and score > 0.5, sorted by score desc."""
    ratings = get_source_ratings(storage, days=days)
    result = []
    for src, bucket in ratings.items():
        if bucket["total"] >= min_feedback and bucket["score"] > 0.5:
            result.append({"source": src, **bucket})
    return result


def get_blocked_sources(storage: Any, days: int = 30, threshold: int = 3) -> list[str]:
    """Sources with >= threshold block (🔕) reactions."""
    ratings = get_source_ratings(storage, days=days)
    return [src for src, b in ratings.items() if b["block"] >= threshold]


def get_user_feedback_stats(storage: Any, user_id: str, days: int = 7) -> dict:
    """Per-user feedback totals over a window.

    Returns {up, down, block, save, total, period_days}.
    """
    result = {"up": 0, "down": 0, "block": 0, "save": 0, "total": 0, "period_days": days}
    if storage is None:
        return result
    try:
        d = int(days)
        if getattr(storage, "is_postgres", False):
            sql = (
                "SELECT rating FROM feedback "
                "WHERE user_id = %s "
                f"AND created_at >= NOW() - INTERVAL '{d} days'"
            )
        else:
            sql = (
                "SELECT rating FROM feedback "
                "WHERE user_id = %s "
                f"AND created_at >= datetime('now', '-{d} days')"
            )
        rows = storage.fetchall(sql, (user_id,))
    except Exception as e:
        logger.warning("[feedback] user stats fetch failed: %s", e)
        return result

    for row in rows:
        rating = _normalize(row.get("rating") or "")
        key = {"blocked": "block", "saved": "save"}.get(rating, rating)
        if key in ("up", "down", "block", "save"):
            result[key] += 1
            result["total"] += 1
    return result
