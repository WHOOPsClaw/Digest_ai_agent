"""cli_stats.py — `newsbrief stats [--days N]` implementation."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from rich.console import Console

logger = logging.getLogger("newsbrief")


def _safe_fetchall(storage, sql: str, params: tuple = ()) -> list:
    try:
        return storage.fetchall(sql, params)
    except Exception as e:
        logger.warning("[stats] query failed: %s", e)
        return []


def _safe_fetchone(storage, sql: str, params: tuple = ()):
    try:
        return storage.fetchone(sql, params)
    except Exception as e:
        logger.warning("[stats] query failed: %s", e)
        return None


def cmd_stats(days: int = 7,
              storage=None,
              console: Optional[Console] = None) -> int:
    if storage is None:
        from newsbrief.core.storage import get_storage
        storage = get_storage()
    console = console or Console()

    since = datetime.now(timezone.utc) - timedelta(days=days)
    since_iso = since.strftime("%Y-%m-%d %H:%M:%S")

    console.print(f"[bold]📊 Stats for last {days} days[/bold]\n")

    # ------------------------------------------------------------------
    # Digests
    # ------------------------------------------------------------------
    digest_rows = _safe_fetchall(
        storage,
        "SELECT COUNT(*) AS n, COALESCE(SUM(item_count), 0) AS items "
        "FROM digests WHERE created_at >= %s AND sent_at IS NOT NULL",
        (since_iso,),
    )
    sent = 0
    total_items = 0
    if digest_rows:
        r = digest_rows[0]
        sent = int(r.get("n") or 0)
        total_items = int(r.get("items") or 0)

    console.print(f"Digests sent: {sent}/{days} " + ("✅" if sent >= days else ""))
    console.print(f"Total cards delivered: {total_items}\n")

    # ------------------------------------------------------------------
    # Feedback
    # ------------------------------------------------------------------
    fb_rows = _safe_fetchall(
        storage,
        "SELECT rating, COUNT(*) AS n FROM feedback "
        "WHERE created_at >= %s GROUP BY rating",
        (since_iso,),
    )
    fb = {str(r.get("rating") or ""): int(r.get("n") or 0) for r in fb_rows}
    liked   = fb.get("like", 0) + fb.get("👍", 0)
    disliked = fb.get("dislike", 0) + fb.get("👎", 0)
    blocked = fb.get("block", 0) + fb.get("🔕", 0)
    saved   = fb.get("save", 0) + fb.get("📌", 0)
    total_fb = liked + disliked

    def _pct(n: int, total: int) -> str:
        return f"({n * 100 // total}%)" if total > 0 else ""

    console.print("[bold]Feedback:[/bold]")
    console.print(f"  👍 Liked: {liked} {_pct(liked, total_items or 1)}")
    console.print(f"  👎 Disliked: {disliked} {_pct(disliked, total_items or 1)}")
    console.print(f"  🔕 Blocked: {blocked}")
    console.print(f"  📌 Saved: {saved}\n")

    # ------------------------------------------------------------------
    # Top sources by 👍
    # ------------------------------------------------------------------
    top_rows = _safe_fetchall(
        storage,
        "SELECT source, COUNT(*) AS n FROM feedback "
        "WHERE created_at >= %s AND rating IN ('like', '👍') "
        "GROUP BY source ORDER BY n DESC LIMIT 5",
        (since_iso,),
    )
    if top_rows:
        console.print("[bold]Top sources (by 👍):[/bold]")
        for i, r in enumerate(top_rows, 1):
            src = r.get("source") or "—"
            n = int(r.get("n") or 0)
            dots = "." * max(1, 30 - len(str(src)))
            console.print(f"  {i}. {src} {dots} {n} 👍")
        console.print()

    # ------------------------------------------------------------------
    # Pipeline runs
    # ------------------------------------------------------------------
    run_rows = _safe_fetchall(
        storage,
        "SELECT status, COUNT(*) AS n, AVG(duration_sec) AS avg_sec, "
        "SUM(llm_calls) AS calls "
        "FROM pipeline_runs WHERE started_at >= %s GROUP BY status",
        (since_iso,),
    )
    succ = fail = 0
    total_calls = 0
    all_avg: list[float] = []
    for r in run_rows:
        n = int(r.get("n") or 0)
        status = str(r.get("status") or "").lower()
        if status == "ok":
            succ += n
        elif status in ("failed", "error"):
            fail += n
        if r.get("avg_sec") is not None:
            all_avg.append(float(r["avg_sec"]))
        if r.get("calls") is not None:
            total_calls += int(r["calls"] or 0)

    avg_dur_row = _safe_fetchone(
        storage,
        "SELECT AVG(duration_sec) AS avg_sec FROM pipeline_runs "
        "WHERE started_at >= %s AND status = 'ok'",
        (since_iso,),
    )
    avg_dur = (avg_dur_row or {}).get("avg_sec") if isinstance(avg_dur_row, dict) else None

    console.print("[bold]LLM:[/bold]")
    console.print(f"  Requests: {total_calls}")
    if avg_dur:
        console.print(f"  Avg pipeline: {float(avg_dur) / 60:.1f} min")
    console.print(f"  Total cost: $0.00 (see provider billing)\n")

    console.print("[bold]Pipeline runs:[/bold]")
    console.print(f"  Succeeded: {succ}")
    console.print(f"  Failed: {fail}")
    if avg_dur:
        console.print(f"  Avg duration: {float(avg_dur):.0f}s")

    return 0
