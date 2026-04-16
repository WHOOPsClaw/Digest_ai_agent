"""cli_sources.py — `newsbrief sources list|validate` command implementations."""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from rich.console import Console
from rich.table import Table

from newsbrief.config import NewsbriefConfig, get_config

logger = logging.getLogger("newsbrief")


# ---------------------------------------------------------------------------
# Helpers — iterate a topic's sources dict into normalized specs
# ---------------------------------------------------------------------------

def iter_topic_sources(topic) -> list[dict[str, Any]]:
    """Flatten a TopicConfig.sources dict into [{type, label, config}, ...]."""
    srcs = topic.sources if isinstance(topic.sources, dict) else {}
    out: list[dict[str, Any]] = []

    for url in (srcs.get("rss") or []):
        out.append({"type": "rss", "label": url, "config": {"url": url}})

    for user in (srcs.get("telegram") or []):
        label = user if user.startswith("@") else f"@{user}"
        out.append({"type": "telegram", "label": label,
                    "config": {"username": user.lstrip("@")}})

    for r in (srcs.get("reddit") or []):
        if isinstance(r, dict):
            sub = r.get("subreddit") or r.get("name") or "?"
            score = r.get("min_score")
            label = f"r/{sub}" + (f" (min_score={score})" if score else "")
            out.append({"type": "reddit", "label": label, "config": r})
        elif isinstance(r, str):
            out.append({"type": "reddit", "label": f"r/{r}",
                        "config": {"subreddit": r}})

    if srcs.get("hackernews"):
        cfg = srcs["hackernews"] if isinstance(srcs["hackernews"], dict) else {}
        out.append({"type": "hackernews", "label": "enabled", "config": cfg})

    for ch in (srcs.get("youtube") or []):
        out.append({"type": "youtube", "label": str(ch),
                    "config": {"channel_id": ch}})

    return out


# ---------------------------------------------------------------------------
# `sources list`
# ---------------------------------------------------------------------------

def cmd_sources_list(cfg: Optional[NewsbriefConfig] = None,
                     console: Optional[Console] = None) -> int:
    cfg = cfg or get_config()
    console = console or Console()

    console.print("[bold]📰 Configured sources[/bold]\n")

    total_sources = 0
    for topic in cfg.topics:
        header = f"━━━ {topic.emoji} {topic.name} (id={topic.id}) ━━━"
        console.print(f"[bold cyan]{header}[/bold cyan]")
        srcs = topic.sources if isinstance(topic.sources, dict) else {}

        rss_list = srcs.get("rss") or []
        if rss_list:
            console.print("  RSS:")
            for url in rss_list:
                console.print(f"    ✅ {url}")
                total_sources += 1

        tg_list = srcs.get("telegram") or []
        if tg_list:
            console.print("  Telegram:")
            for u in tg_list:
                label = u if str(u).startswith("@") else f"@{u}"
                console.print(f"    ✅ {label}")
                total_sources += 1

        reddit_list = srcs.get("reddit") or []
        if reddit_list:
            console.print("  Reddit:")
            for r in reddit_list:
                if isinstance(r, dict):
                    sub = r.get("subreddit") or r.get("name") or "?"
                    score = r.get("min_score")
                    extra = f" (min_score={score})" if score else ""
                    console.print(f"    ✅ r/{sub}{extra}")
                else:
                    console.print(f"    ✅ r/{r}")
                total_sources += 1

        if srcs.get("hackernews"):
            console.print("  HackerNews: enabled")
            total_sources += 1

        yt_list = srcs.get("youtube") or []
        if yt_list:
            console.print("  YouTube:")
            for ch in yt_list:
                console.print(f"    ✅ {ch}")
                total_sources += 1

        console.print()

    console.print(f"[bold]Total:[/bold] {len(cfg.topics)} topics, "
                  f"{total_sources} sources")
    return 0


# ---------------------------------------------------------------------------
# `sources validate`
# ---------------------------------------------------------------------------

def _humanize_age(dt: Optional[datetime]) -> str:
    if dt is None:
        return "—"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - dt
    secs = delta.total_seconds()
    if secs < 0:
        return "future"
    if secs < 60:
        return f"{int(secs)}s ago"
    if secs < 3600:
        return f"{int(secs // 60)}m ago"
    if secs < 86400:
        return f"{int(secs // 3600)}h ago"
    return f"{int(secs // 86400)}d ago"


def _classify(last_post: Optional[datetime]) -> str:
    if last_post is None:
        return "stale"
    if last_post.tzinfo is None:
        last_post = last_post.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - last_post
    # more than 2 days → stale, otherwise live
    if delta.total_seconds() > 2 * 86400:
        return "stale"
    return "live"


def _validate_one(spec: dict[str, Any], timeout: float = 15.0) -> dict[str, Any]:
    """Validate a single source. Returns dict with status/last_post/error."""
    from newsbrief.sources import get_provider
    stype = spec["type"]
    label = spec["label"]
    provider = get_provider(stype)

    result = {
        "type": stype,
        "label": label,
        "status": "error",
        "last_post": None,
        "error": "",
    }

    if provider is None:
        result["error"] = f"no provider for '{stype}'"
        return result

    # Schema validation first.
    cfg = dict(spec.get("config") or {})
    try:
        errs = provider.validate_config(cfg)
        if errs:
            result["error"] = "; ".join(errs)
            return result
    except Exception as e:
        result["error"] = f"validate_config: {e}"
        return result

    # Live fetch — single item.
    try:
        items = list(provider.fetch(cfg, limit=1))
    except Exception as e:
        result["error"] = str(e)[:80]
        return result

    if not items:
        result["status"] = "stale"
        return result

    last = items[0].published_at
    result["last_post"] = last
    result["status"] = _classify(last)
    return result


def cmd_sources_validate(cfg: Optional[NewsbriefConfig] = None,
                         console: Optional[Console] = None,
                         max_workers: int = 8,
                         timeout: float = 15.0) -> int:
    cfg = cfg or get_config()
    console = console or Console()

    # Collect all specs across topics.
    specs: list[dict[str, Any]] = []
    for topic in cfg.topics:
        for s in iter_topic_sources(topic):
            specs.append(s)

    if not specs:
        console.print("[yellow]No sources configured.[/yellow]")
        return 0

    console.print(f"[bold]Validating {len(specs)} source(s)...[/bold]\n")

    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(_validate_one, s, timeout): s for s in specs}
        for fut in as_completed(futs):
            try:
                results.append(fut.result(timeout=timeout + 5))
            except Exception as e:
                spec = futs[fut]
                results.append({
                    "type": spec["type"], "label": spec["label"],
                    "status": "error", "last_post": None,
                    "error": str(e)[:80],
                })

    # Stable-sort by type then label for readable output.
    results.sort(key=lambda r: (r["type"], r["label"]))

    table = Table(show_lines=False)
    table.add_column("Source", overflow="fold")
    table.add_column("Status")
    table.add_column("Last post")

    icon = {"live": "✅ live", "stale": "⚠️ stale", "error": "❌ error"}
    counts = {"live": 0, "stale": 0, "error": 0}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
        last_col = (r["error"] or "—") if r["status"] == "error" \
                   else _humanize_age(r["last_post"])
        table.add_row(f"{r['type']}: {r['label']}",
                      icon.get(r["status"], r["status"]),
                      last_col)

    console.print(table)
    console.print(
        f"\n[bold]Summary:[/bold] {counts['live']} live, "
        f"{counts['stale']} stale, {counts['error']} error"
    )
    return 0 if counts["error"] == 0 else 1
