"""YouTube channel/playlist source provider (via videos.xml feed)."""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Iterator

import feedparser
import httpx

from newsbrief.core.models import RawArticle
from newsbrief.sources.base import SourceProvider
from newsbrief.utils.image_extractor import extract_image_from_feedparser_entry

logger = logging.getLogger(__name__)

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_USER_AGENT = "Mozilla/5.0 (compatible; newsbrief/1.0)"


def _parse_published(entry) -> datetime | None:
    for attr in ("published_parsed", "updated_parsed"):
        t = getattr(entry, attr, None)
        if t is not None:
            try:
                return datetime(*t[:6], tzinfo=timezone.utc)
            except Exception:
                pass
    return None


def _media_desc(entry) -> str:
    # feedparser exposes media:description as media_description or under media_group
    raw = getattr(entry, "media_description", None) or getattr(entry, "summary", "") or ""
    mg = getattr(entry, "media_group", None)
    if not raw and isinstance(mg, dict):
        raw = mg.get("media_description", "") or ""
    return _HTML_TAG_RE.sub("", raw).strip()[:300]


class YouTubeProvider(SourceProvider):
    provider_id = "youtube"

    def validate_config(self, config: dict) -> list[str]:
        errors: list[str] = []
        if not config.get("channel_id") and not config.get("playlist_id"):
            errors.append("either channel_id or playlist_id is required")
        return errors

    def describe(self, config: dict) -> str:
        if config.get("channel_id"):
            return f"youtube:channel/{config['channel_id']}"
        return f"youtube:playlist/{config.get('playlist_id', '?')}"

    def fetch(self, config: dict, limit: int = 20) -> Iterator[RawArticle]:
        category = config.get("category", "")
        if config.get("channel_id"):
            cid = config["channel_id"]
            feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}"
            source = f"youtube:{cid[:8]}"
        else:
            pid = config["playlist_id"]
            feed_url = f"https://www.youtube.com/feeds/videos.xml?playlist_id={pid}"
            source = f"youtube:{pid[:8]}"

        try:
            with httpx.Client(timeout=15.0, follow_redirects=True) as client:
                resp = client.get(feed_url, headers={"User-Agent": _USER_AGENT})
                resp.raise_for_status()
                text = resp.text
        except Exception as e:
            logger.warning("youtube fetch failed url=%s: %s", feed_url, e)
            return

        parsed = feedparser.parse(text)
        if parsed.bozo and not parsed.entries:
            logger.warning("youtube bozo url=%s", feed_url)
            return

        for entry in parsed.entries[:limit]:
            link = (getattr(entry, "link", None) or "").strip()
            title = (getattr(entry, "title", None) or "").strip()
            if not link or not title:
                continue
            image_url = None
            try:
                image_url = extract_image_from_feedparser_entry(entry)
            except Exception:
                image_url = None
            yield RawArticle(
                category=category,
                title=title,
                url=link,
                snippet=_media_desc(entry),
                source=source,
                published_at=_parse_published(entry),
                role="source",
                image_url=image_url,
            )
