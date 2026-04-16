"""Optional auto-discovery of NEW RSS feeds via web search."""
from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

logger = logging.getLogger(__name__)

_USER_AGENT = "Mozilla/5.0 (compatible; newsbrief-discovery/1.0)"
_FEED_CANDIDATES = ["/feed", "/feed/", "/rss", "/rss.xml", "/atom.xml", "/index.xml"]
_LINK_RE = re.compile(
    r'<link[^>]+rel=["\']alternate["\'][^>]+type=["\']application/(?:rss|atom)\+xml["\'][^>]*>',
    re.IGNORECASE,
)
_HREF_RE = re.compile(r'href=["\']([^"\']+)["\']', re.IGNORECASE)


def _generate_queries(topic: str, llm_router: Any) -> list[str]:
    prompt = (
        f"Suggest 3 short web-search queries to find RSS feeds for '{topic}'. "
        "Return one per line, no numbering, no quotes."
    )
    try:
        resp = llm_router.generate(prompt, task="discovery", max_tokens=200)
        text = getattr(resp, "text", "") or ""
        queries = [ln.strip(" -*\"'") for ln in text.splitlines() if ln.strip()]
        queries = [q for q in queries if len(q) > 3][:3]
        if queries:
            return queries
    except Exception as e:
        logger.warning("LLM query-gen failed: %s", e)
    return [
        f"best RSS feed for {topic}",
        f"{topic} blog RSS",
        f"{topic} news feed",
    ]


def _search(query: str) -> list[str]:
    """Run a search via newsbrief.sources.search if available. Returns list of URLs."""
    try:
        from newsbrief.sources.search import SearchProvider  # type: ignore

        provider = SearchProvider()
        results = provider.fetch({"query": query}, limit=10)
        urls: list[str] = []
        for item in results:
            url = getattr(item, "url", None)
            if url:
                urls.append(url)
        if urls:
            return urls
    except Exception as e:
        logger.debug("search provider unavailable: %s", e)
    return []


def _extract_feed_from_html(html: str, base_url: str) -> list[str]:
    feeds: list[str] = []
    for tag in _LINK_RE.findall(html):
        m = _HREF_RE.search(tag)
        if m:
            href = m.group(1)
            feeds.append(urljoin(base_url, href))
    return feeds


def _probe_url_for_feed(url: str, timeout: int = 10) -> list[str]:
    candidates: list[str] = []
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.get(url, headers={"User-Agent": _USER_AGENT})
            if resp.status_code == 200:
                ct = resp.headers.get("content-type", "").lower()
                if "xml" in ct or "rss" in ct or "atom" in ct:
                    candidates.append(str(resp.url))
                else:
                    candidates.extend(_extract_feed_from_html(resp.text, str(resp.url)))

            # Try well-known endpoints.
            parsed = urlparse(url)
            root = f"{parsed.scheme}://{parsed.netloc}"
            for suffix in _FEED_CANDIDATES:
                try:
                    r = client.head(root + suffix)
                    if r.status_code < 400:
                        candidates.append(root + suffix)
                except Exception:
                    continue
    except Exception as e:
        logger.debug("probe failed url=%s: %s", url, e)
    # Deduplicate, preserve order.
    seen: set[str] = set()
    out: list[str] = []
    for u in candidates:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def discover_rss_for_topic(topic: str, llm_router: Any) -> list[dict[str, Any]]:
    """Use LLM + web search to discover RSS feeds for an arbitrary topic."""
    from newsbrief.discovery.validator import validate_source

    queries = _generate_queries(topic, llm_router)
    candidate_urls: list[str] = []
    for q in queries:
        candidate_urls.extend(_search(q))

    seen_feeds: set[str] = set()
    discovered: list[dict[str, Any]] = []
    for url in candidate_urls[:20]:
        for feed_url in _probe_url_for_feed(url):
            if feed_url in seen_feeds:
                continue
            seen_feeds.add(feed_url)
            spec = {"type": "rss", "url": feed_url}
            v = validate_source(spec)
            if v.get("valid"):
                discovered.append(
                    {
                        "type": "rss",
                        "url": feed_url,
                        "name": urlparse(feed_url).netloc,
                        "validation": v,
                    }
                )
    return discovered
