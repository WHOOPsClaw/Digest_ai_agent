"""Weekly/monthly statistics aggregation for `newsbrief stats`."""
from __future__ import annotations

from collections import Counter
from typing import Any


def compute_stats(storage, days: int = 7) -> dict[str, Any]:
    """Aggregate pipeline_runs, feedback, digests over the last `days` days.

    Returns a dict suitable for rendering (via rich) or JSON export.
    """
    # All SQL uses SQLite date math; works under our SQLite adapter.
    # For Postgres this would need `NOW() - INTERVAL '%s days'` — out of scope.
    since_expr = f"datetime('now', '-{int(days)} days')"

    digests = _safe_fetchall(
        storage,
        f"SELECT COUNT(*) AS n FROM digests WHERE created_at >= {since_expr}",
    )
    digest_count = (digests[0].get("n") if digests else 0) or 0

    items_row = _safe_fetchall(
        storage,
        f"SELECT COALESCE(SUM(item_count), 0) AS n FROM digests WHERE created_at >= {since_expr}",
    )
    total_items = (items_row[0].get("n") if items_row else 0) or 0

    runs = _safe_fetchall(
        storage,
        f"SELECT duration_sec FROM pipeline_runs "
        f"WHERE started_at >= {since_expr} AND duration_sec IS NOT NULL",
    )
    durations = [r.get("duration_sec") for r in runs if r.get("duration_sec")]
    avg_duration_sec = sum(durations) / len(durations) if durations else 0.0

    fb = _safe_fetchall(
        storage,
        f"SELECT rating, source FROM feedback WHERE created_at >= {since_expr}",
    )
    rating_counts: Counter[str] = Counter()
    source_likes: Counter[str] = Counter()
    for row in fb:
        r = (row.get("rating") or "").strip()
        if r:
            rating_counts[r] += 1
        if r in ("like", "👍") and row.get("source"):
            source_likes[row["source"]] += 1

    total_reactions = sum(rating_counts.values())

    top_sources = source_likes.most_common(5)

    return {
        "days": days,
        "digest_count": int(digest_count),
        "digest_expected": days,
        "total_items": int(total_items),
        "avg_duration_sec": float(avg_duration_sec),
        "reactions": dict(rating_counts),
        "total_reactions": total_reactions,
        "top_sources": top_sources,
    }


def _safe_fetchall(storage, sql: str) -> list:
    try:
        return storage.fetchall(sql) or []
    except Exception:
        return []
