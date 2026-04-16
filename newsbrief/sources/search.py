"""Web search source provider (SearXNG / Brave / DuckDuckGo fallback)."""
from __future__ import annotations

import html
import logging
import re
from typing import Iterator
from urllib.parse import quote_plus, unquote

import httpx

from newsbrief.core.models import RawArticle
from newsbrief.sources.base import SourceProvider

logger = logging.getLogger(__name__)

_USER_AGENT = "Mozilla/5.0 (compatible; newsbrief/1.0)"
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_VALID_ENGINES = {"searxng", "brave", "ddg"}


def _strip_html(s: str) -> str:
    return html.unescape(_HTML_TAG_RE.sub("", s or "")).strip()


class SearchProvider(SourceProvider):
    provider_id = "search"

    def validate_config(self, config: dict) -> list[str]:
        errors: list[str] = []
        if not config.get("query"):
            errors.append("query is required")
        engine = config.get("engine", "ddg")
        if engine not in _VALID_ENGINES:
            errors.append(f"engine must be one of {_VALID_ENGINES}")
        if engine == "searxng" and not config.get("base_url"):
            errors.append("base_url is required for searxng")
        if engine == "brave" and not config.get("api_key"):
            errors.append("api_key is required for brave")
        return errors

    def describe(self, config: dict) -> str:
        return f"search[{config.get('engine', 'ddg')}]:{config.get('query', '?')}"

    def fetch(self, config: dict, limit: int = 20) -> Iterator[RawArticle]:
        query = config["query"]
        engine = config.get("engine", "ddg")
        fetch_limit = int(config.get("limit", 10))
        category = config.get("category", "")
        n = min(limit, fetch_limit)

        if engine == "searxng":
            yield from self._searxng(config, query, n, category)
        elif engine == "brave":
            yield from self._brave(config, query, n, category)
        else:
            yield from self._ddg(query, n, category)

    # ---- engines ----

    def _make_article(self, category: str, title: str, url: str, snippet: str) -> RawArticle:
        return RawArticle(
            category=category,
            title=title,
            url=url,
            snippet=snippet[:300],
            source="search",
            role="signal",
        )

    def _searxng(self, config: dict, query: str, n: int, category: str) -> Iterator[RawArticle]:
        base = config["base_url"].rstrip("/")
        try:
            with httpx.Client(timeout=15.0, follow_redirects=True) as client:
                resp = client.get(
                    f"{base}/search",
                    params={"q": query, "format": "json"},
                    headers={"User-Agent": _USER_AGENT},
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            logger.warning("searxng fetch failed: %s", e)
            return

        for r in (data.get("results") or [])[:n]:
            url = (r.get("url") or "").strip()
            title = (r.get("title") or "").strip()
            if not url or not title:
                continue
            yield self._make_article(category, title, url, r.get("content") or "")

    def _brave(self, config: dict, query: str, n: int, category: str) -> Iterator[RawArticle]:
        key = config["api_key"]
        try:
            with httpx.Client(timeout=15.0, follow_redirects=True) as client:
                resp = client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    params={"q": query, "count": n},
                    headers={
                        "X-Subscription-Token": key,
                        "Accept": "application/json",
                        "User-Agent": _USER_AGENT,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            logger.warning("brave fetch failed: %s", e)
            return

        results = ((data.get("web") or {}).get("results")) or []
        for r in results[:n]:
            url = (r.get("url") or "").strip()
            title = _strip_html(r.get("title") or "")
            if not url or not title:
                continue
            yield self._make_article(category, title, url, _strip_html(r.get("description") or ""))

    def _ddg(self, query: str, n: int, category: str) -> Iterator[RawArticle]:
        try:
            with httpx.Client(timeout=15.0, follow_redirects=True) as client:
                resp = client.get(
                    f"https://duckduckgo.com/html/?q={quote_plus(query)}",
                    headers={"User-Agent": _USER_AGENT},
                )
                resp.raise_for_status()
                html_text = resp.text
        except Exception as e:
            logger.warning("ddg fetch failed: %s", e)
            return

        # Result blocks: <a ... class="result__a" href="...">TITLE</a> and
        # <a class="result__snippet" ...>SNIPPET</a>
        result_re = re.compile(
            r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
            re.DOTALL | re.IGNORECASE,
        )
        snippet_re = re.compile(
            r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>',
            re.DOTALL | re.IGNORECASE,
        )
        hits = result_re.findall(html_text)
        snippets = snippet_re.findall(html_text)

        yielded = 0
        for i, (raw_url, raw_title) in enumerate(hits):
            if yielded >= n:
                break
            # DDG redirects via /l/?uddg=<encoded>
            url = raw_url
            m = re.search(r"[?&]uddg=([^&]+)", url)
            if m:
                url = unquote(m.group(1))
            title = _strip_html(raw_title)
            snippet = _strip_html(snippets[i]) if i < len(snippets) else ""
            if not url or not title:
                continue
            yield self._make_article(category, title, url, snippet)
            yielded += 1
