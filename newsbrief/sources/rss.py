"""RSS source provider."""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Iterator
from urllib.parse import urlparse

import feedparser
import httpx

from newsbrief.core.models import RawArticle
from newsbrief.sources.base import SourceProvider

logger = logging.getLogger(__name__)

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_USER_AGENT = "Mozilla/5.0 (compatible; newsbrief/1.0; +https://github.com/newsbrief)"


def _parse_published(entry) -> datetime | None:
    for attr in ("published_parsed", "updated_parsed"):
        t = getattr(entry, attr, None)
        if t is not None:
            try:
                return datetime(*t[:6], tzinfo=timezone.utc)
            except Exception:
                pass
    return None


def _entry_snippet(entry) -> str:
    raw = ""
    if hasattr(entry, "summary"):
        raw = entry.summary
    elif hasattr(entry, "content") and entry.content:
        raw = entry.content[0].get("value", "")
    return _HTML_TAG_RE.sub("", raw).strip()[:300]


class RSSProvider(SourceProvider):
    provider_id = "rss"

    def validate_config(self, config: dict) -> list[str]:
        errors: list[str] = []
        url = config.get("url")
        if not url:
            errors.append("url is required")
            return errors
        if not isinstance(url, str):
            errors.append("url must be a string")
            return errors
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            errors.append(f"invalid url: {url}")
        return errors

    def describe(self, config: dict) -> str:
        return f"rss:{config.get('url', '?')}"

    def fetch(self, config: dict, limit: int = 20) -> Iterator[RawArticle]:
        url = config["url"]
        category = config.get("category", "")
        role = config.get("role", "source")

        try:
            with httpx.Client(timeout=15.0, follow_redirects=True) as client:
                resp = client.get(url, headers={"User-Agent": _USER_AGENT})
                resp.raise_for_status()
                text = resp.text
        except Exception as e:
            logger.warning("rss fetch failed url=%s: %s", url, e)
            return

        parsed = feedparser.parse(text)
        if parsed.bozo and not parsed.entries:
            logger.warning("rss bozo url=%s: %s", url, getattr(parsed, "bozo_exception", "?"))
            return

        domain = urlparse(url).netloc.lower().replace("www.", "")
        source = f"rss:{domain}"

        for entry in parsed.entries[:limit]:
            link = (getattr(entry, "link", None) or "").strip()
            title = (getattr(entry, "title", None) or "").strip()
            if not link or not title:
                continue
            yield RawArticle(
                category=category,
                title=title,
                url=link,
                snippet=_entry_snippet(entry),
                source=source,
                published_at=_parse_published(entry),
                role=role,
            )
