"""Generate TopicConfig-compatible dicts from discovery matches + selections."""
from __future__ import annotations

from typing import Any, Iterable


def source_id(src: dict[str, Any]) -> str:
    """Stable ID for a source spec (used to match user selections)."""
    stype = src.get("type") or ""
    if stype == "rss":
        return f"rss:{src.get('url', '')}"
    if stype == "telegram":
        cfg = src.get("config") or {}
        return f"telegram:{cfg.get('username', '')}"
    if stype == "reddit":
        cfg = src.get("config") or {}
        return f"reddit:{cfg.get('sub', '')}"
    if stype == "hackernews":
        cfg = src.get("config") or {}
        return f"hackernews:{cfg.get('type', 'top')}"
    if stype == "youtube":
        cfg = src.get("config") or {}
        return f"youtube:{cfg.get('channel_id') or cfg.get('channel', '')}"
    return f"{stype}:{src.get('name', '')}"


def generate_topics_yaml(
    matched: list[dict[str, Any]],
    selected_source_ids: Iterable[str],
) -> list[dict[str, Any]]:
    """Convert discovery results + user selections into TopicConfig dicts."""
    selected = set(selected_source_ids or [])
    topics: list[dict[str, Any]] = []

    for topic in matched or []:
        tid = topic.get("topic_id") or ""
        name = topic.get("display_name") or tid
        emoji = topic.get("emoji") or "📰"

        rss_urls: list[str] = []
        telegram_users: list[str] = []
        reddit_subs: list[dict[str, Any]] = []
        hackernews_on = False
        youtube_channels: list[str] = []

        for entry in topic.get("sources", []) or []:
            src = entry.get("source_ref") or entry
            sid = source_id(src)
            if sid not in selected:
                continue
            stype = src.get("type")
            cfg = src.get("config") or {}
            if stype == "rss":
                url = src.get("url") or cfg.get("url")
                if url and url not in rss_urls:
                    rss_urls.append(url)
            elif stype == "telegram":
                u = cfg.get("username")
                if u and u not in telegram_users:
                    telegram_users.append(u)
            elif stype == "reddit":
                if cfg and cfg not in reddit_subs:
                    reddit_subs.append(dict(cfg))
            elif stype == "hackernews":
                hackernews_on = True
            elif stype == "youtube":
                ch = cfg.get("channel_id") or cfg.get("channel")
                if ch and ch not in youtube_channels:
                    youtube_channels.append(ch)

        sources: dict[str, Any] = {}
        if rss_urls:
            sources["rss"] = rss_urls
        if telegram_users:
            sources["telegram"] = telegram_users
        if reddit_subs:
            sources["reddit"] = reddit_subs
        if hackernews_on:
            sources["hackernews"] = True
        if youtube_channels:
            sources["youtube"] = youtube_channels

        if not sources:
            continue

        topics.append(
            {
                "id": tid,
                "name": name,
                "emoji": emoji,
                "sources": sources,
                "items_per_digest": 5,
            }
        )

    return topics
