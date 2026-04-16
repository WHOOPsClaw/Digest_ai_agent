"""Reddit subreddit source provider (public JSON endpoint)."""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Iterator

import httpx

from newsbrief.core.models import RawArticle
from newsbrief.sources.base import SourceProvider
from newsbrief.utils.image_extractor import extract_image_from_reddit

logger = logging.getLogger(__name__)

_USER_AGENT = "Mozilla/5.0 (compatible; newsbrief/1.0)"


class RedditProvider(SourceProvider):
    provider_id = "reddit"

    def validate_config(self, config: dict) -> list[str]:
        errors: list[str] = []
        sub = config.get("sub")
        if not sub:
            errors.append("sub is required")
        elif not isinstance(sub, str) or not re.match(r"^[A-Za-z0-9_]{2,50}$", sub):
            errors.append(f"invalid subreddit: {sub}")
        ms = config.get("min_score", 50)
        if not isinstance(ms, int) or ms < 0:
            errors.append("min_score must be a non-negative int")
        return errors

    def describe(self, config: dict) -> str:
        return f"reddit:r/{config.get('sub', '?')}"

    def fetch(self, config: dict, limit: int = 20) -> Iterator[RawArticle]:
        sub = config["sub"]
        min_score = int(config.get("min_score", 50))
        fetch_limit = int(config.get("limit", 25))
        category = config.get("category", "")

        url = f"https://www.reddit.com/r/{sub}/hot.json?limit={fetch_limit}"

        try:
            with httpx.Client(timeout=15.0, follow_redirects=True) as client:
                resp = client.get(url, headers={"User-Agent": _USER_AGENT})
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            logger.warning("reddit fetch failed sub=%s: %s", sub, e)
            return

        children = (data.get("data") or {}).get("children") or []
        source = f"reddit:{sub}"
        yielded = 0

        for ch in children:
            if yielded >= limit:
                break
            d = ch.get("data") or {}
            score = int(d.get("score") or 0)
            if score < min_score:
                continue
            title = (d.get("title") or "").strip()
            link_url = (d.get("url") or "").strip()
            permalink = d.get("permalink") or ""
            if permalink and not link_url.startswith("http"):
                link_url = f"https://www.reddit.com{permalink}"
            if not title or not link_url:
                continue
            snippet = (d.get("selftext") or "").strip()[:300]
            pub_at: datetime | None = None
            created = d.get("created_utc")
            if created:
                try:
                    pub_at = datetime.fromtimestamp(float(created), tz=timezone.utc)
                except Exception:
                    pass

            image_url = None
            try:
                image_url = extract_image_from_reddit(d)
            except Exception:
                image_url = None
            yield RawArticle(
                category=category,
                title=title,
                url=link_url,
                snippet=snippet,
                source=source,
                published_at=pub_at,
                role="source",
                image_url=image_url,
            )
            yielded += 1
