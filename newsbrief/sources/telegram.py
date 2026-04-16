"""Telegram public channel source provider (scrapes t.me/s/{user})."""
from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Iterator

import httpx

from newsbrief.core.models import RawArticle
from newsbrief.sources.base import SourceProvider

logger = logging.getLogger(__name__)

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_TG_MSG_RE = re.compile(
    r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>',
    re.DOTALL | re.IGNORECASE,
)
_TG_TIME_RE = re.compile(r'<time[^>]+datetime="([^"]+)"', re.IGNORECASE)
_TG_MSGLINK_RE = re.compile(r'href="(https://t\.me/[^/]+/\d+)"', re.IGNORECASE)

_USER_AGENT = "Mozilla/5.0 (compatible; Googlebot/2.1)"


def _clean(html: str) -> str:
    text = _HTML_TAG_RE.sub(" ", html)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:500]


def _title_from(text: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if len(line) >= 20:
            return line[:120]
    return text[:120].strip()


class TelegramProvider(SourceProvider):
    provider_id = "telegram"

    def validate_config(self, config: dict) -> list[str]:
        errors: list[str] = []
        username = config.get("username")
        if not username:
            errors.append("username is required")
        elif not isinstance(username, str):
            errors.append("username must be a string")
        elif not re.match(r"^[A-Za-z0-9_]{3,64}$", username):
            errors.append(f"invalid telegram username: {username}")
        return errors

    def describe(self, config: dict) -> str:
        return f"tg:{config.get('username', '?')}"

    def fetch(self, config: dict, limit: int = 20) -> Iterator[RawArticle]:
        username = config["username"]
        category = config.get("category", "")
        url = f"https://t.me/s/{username}"

        try:
            with httpx.Client(timeout=15.0, follow_redirects=True) as client:
                resp = client.get(url, headers={"User-Agent": _USER_AGENT})
            if resp.status_code != 200:
                logger.warning("tg channel=%s status=%d", username, resp.status_code)
                return
            html = resp.text
        except Exception as e:
            logger.warning("tg fetch failed channel=%s: %s", username, e)
            return

        msg_texts = _TG_MSG_RE.findall(html)
        timestamps = _TG_TIME_RE.findall(html)
        msg_links = _TG_MSGLINK_RE.findall(html)

        # Take most recent `limit` posts (they appear in chronological order).
        recent = msg_texts[-limit:]
        offset = len(msg_texts) - len(recent)

        source = f"tg:{username}"

        for i, raw_html in enumerate(recent):
            text = _clean(raw_html)
            if len(text) < 30:
                continue
            if not re.search(r"[а-яёa-z]{4,}", text, re.IGNORECASE):
                continue

            idx = offset + i
            post_url = msg_links[idx] if idx < len(msg_links) else url

            pub_at: datetime | None = None
            if idx < len(timestamps):
                try:
                    pub_at = datetime.fromisoformat(timestamps[idx].replace("Z", "+00:00"))
                except Exception:
                    pass

            yield RawArticle(
                category=category,
                title=_title_from(text),
                url=post_url,
                snippet=text[:300],
                source=source,
                published_at=pub_at,
                role="signal",
            )
