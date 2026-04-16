"""Hacker News source provider (firebase API, parallel item fetch)."""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Iterator

import httpx

from newsbrief.core.models import RawArticle
from newsbrief.sources.base import SourceProvider

logger = logging.getLogger(__name__)

_BASE = "https://hacker-news.firebaseio.com/v0"
_VALID_TYPES = {"top", "new", "best"}


def _fetch_item(client: httpx.Client, item_id: int) -> dict | None:
    try:
        r = client.get(f"{_BASE}/item/{item_id}.json")
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.debug("hn item %d failed: %s", item_id, e)
        return None


class HackerNewsProvider(SourceProvider):
    provider_id = "hackernews"

    def validate_config(self, config: dict) -> list[str]:
        errors: list[str] = []
        t = config.get("type", "top")
        if t not in _VALID_TYPES:
            errors.append(f"type must be one of {_VALID_TYPES}, got {t!r}")
        ms = config.get("min_score", 50)
        if not isinstance(ms, int) or ms < 0:
            errors.append("min_score must be non-negative int")
        return errors

    def describe(self, config: dict) -> str:
        return f"hackernews:{config.get('type', 'top')}"

    def fetch(self, config: dict, limit: int = 20) -> Iterator[RawArticle]:
        story_type = config.get("type", "top")
        fetch_limit = int(config.get("limit", 30))
        min_score = int(config.get("min_score", 50))
        category = config.get("category", "")

        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.get(f"{_BASE}/{story_type}stories.json")
                resp.raise_for_status()
                ids = resp.json() or []
        except Exception as e:
            logger.warning("hn list fetch failed type=%s: %s", story_type, e)
            return

        ids = ids[:fetch_limit]

        items: list[dict] = []
        try:
            with httpx.Client(timeout=15.0) as client:
                with ThreadPoolExecutor(max_workers=8) as ex:
                    results = list(ex.map(lambda i: _fetch_item(client, i), ids))
            items = [r for r in results if r]
        except Exception as e:
            logger.warning("hn items fetch failed: %s", e)
            return

        yielded = 0
        for it in items:
            if yielded >= limit:
                break
            score = int(it.get("score") or 0)
            if score < min_score:
                continue
            url = (it.get("url") or "").strip()
            if not url:  # skip Ask HN / text posts
                continue
            title = (it.get("title") or "").strip()
            if not title:
                continue
            pub_at: datetime | None = None
            t = it.get("time")
            if t:
                try:
                    pub_at = datetime.fromtimestamp(float(t), tz=timezone.utc)
                except Exception:
                    pass
            hn_id = it.get("id")
            snippet = f"HN score={score} comments={it.get('descendants', 0)}"
            yield RawArticle(
                category=category,
                title=title,
                url=url,
                snippet=snippet,
                source="hackernews",
                published_at=pub_at,
                role="source",
            )
            yielded += 1
            _ = hn_id  # available for future use
