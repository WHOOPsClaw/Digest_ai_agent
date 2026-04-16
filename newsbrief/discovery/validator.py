"""Source validation — check a source spec is live and recent."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_USER_AGENT = "Mozilla/5.0 (compatible; newsbrief-discovery/1.0)"


def _result(valid: bool, **kwargs: Any) -> dict[str, Any]:
    base = {
        "valid": valid,
        "last_post_age_days": kwargs.get("last_post_age_days", -1),
        "items_recent": kwargs.get("items_recent", 0),
        "error": kwargs.get("error", ""),
    }
    return base


def _validate_rss(spec: dict, timeout: int) -> dict[str, Any]:
    import feedparser

    url = spec.get("url") or (spec.get("config") or {}).get("url")
    if not url:
        return _result(False, error="no url")
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.get(url, headers={"User-Agent": _USER_AGENT})
            resp.raise_for_status()
            text = resp.text
    except Exception as e:
        return _result(False, error=f"fetch: {e}")

    parsed = feedparser.parse(text)
    entries = list(getattr(parsed, "entries", []) or [])
    if not entries:
        return _result(False, error="no entries")

    latest: datetime | None = None
    for entry in entries:
        for attr in ("published_parsed", "updated_parsed"):
            t = getattr(entry, attr, None)
            if t is not None:
                try:
                    d = datetime(*t[:6], tzinfo=timezone.utc)
                    if latest is None or d > latest:
                        latest = d
                except Exception:
                    pass
    age_days = -1
    if latest is not None:
        age_days = (datetime.now(timezone.utc) - latest).days
    valid = len(entries) > 0 and (age_days == -1 or age_days < 60)
    return _result(
        valid,
        last_post_age_days=age_days,
        items_recent=len(entries),
        error="" if valid else "stale feed",
    )


def _validate_telegram(spec: dict, timeout: int) -> dict[str, Any]:
    cfg = spec.get("config") or {}
    user = cfg.get("username") or spec.get("username")
    if not user:
        return _result(False, error="no username")
    url = f"https://t.me/s/{user}"
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.get(url, headers={"User-Agent": _USER_AGENT})
            if resp.status_code != 200:
                return _result(False, error=f"http {resp.status_code}")
            text = resp.text
    except Exception as e:
        return _result(False, error=f"fetch: {e}")
    count = text.count("tgme_widget_message")
    if count == 0:
        return _result(False, error="no messages on page")
    return _result(True, items_recent=count)


def _validate_reddit(spec: dict, timeout: int) -> dict[str, Any]:
    cfg = spec.get("config") or {}
    sub = cfg.get("sub") or spec.get("sub")
    if not sub:
        return _result(False, error="no sub")
    url = f"https://www.reddit.com/r/{sub}/about.json"
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.get(url, headers={"User-Agent": _USER_AGENT})
            if resp.status_code != 200:
                return _result(False, error=f"http {resp.status_code}")
            data = resp.json()
    except Exception as e:
        return _result(False, error=f"fetch: {e}")
    if not isinstance(data, dict) or "data" not in data:
        return _result(False, error="bad response")
    return _result(True, items_recent=1)


def _validate_hackernews(spec: dict, timeout: int) -> dict[str, Any]:
    return _result(True, items_recent=1)


def _validate_youtube(spec: dict, timeout: int) -> dict[str, Any]:
    cfg = spec.get("config") or {}
    channel = cfg.get("channel_id") or cfg.get("channel") or spec.get("channel_id")
    if not channel:
        return _result(False, error="no channel_id")
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel}"
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.get(url, headers={"User-Agent": _USER_AGENT})
            if resp.status_code != 200:
                return _result(False, error=f"http {resp.status_code}")
    except Exception as e:
        return _result(False, error=f"fetch: {e}")
    return _result(True, items_recent=1)


def validate_source(source_spec: dict, timeout: int = 15) -> dict[str, Any]:
    """Validate a source spec. Returns {valid, last_post_age_days, items_recent, error}."""
    if not isinstance(source_spec, dict):
        return _result(False, error="invalid spec")
    stype = source_spec.get("type") or ""
    try:
        if stype == "rss":
            return _validate_rss(source_spec, timeout)
        if stype == "telegram":
            return _validate_telegram(source_spec, timeout)
        if stype == "reddit":
            return _validate_reddit(source_spec, timeout)
        if stype == "hackernews":
            return _validate_hackernews(source_spec, timeout)
        if stype == "youtube":
            return _validate_youtube(source_spec, timeout)
    except Exception as e:
        return _result(False, error=f"exception: {e}")
    return _result(False, error=f"unknown type: {stype}")
