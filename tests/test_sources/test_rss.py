"""Tests for RSSProvider using httpx MockTransport."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import httpx

from newsbrief.sources.rss import RSSProvider

FIXTURE = Path(__file__).parent.parent / "fixtures" / "rss_feed.xml"


def _mock_client(body: str, status: int = 200):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text=body, headers={"content-type": "application/xml"})
    transport = httpx.MockTransport(handler)
    return transport


def test_rss_validate_config_requires_url():
    p = RSSProvider()
    assert p.validate_config({}) == ["url is required"]
    assert p.validate_config({"url": "not-a-url"}) == ["invalid url: not-a-url"]
    assert p.validate_config({"url": "https://example.com/feed"}) == []


def test_rss_fetch_parses_entries():
    body = FIXTURE.read_text()
    transport = _mock_client(body)

    original_client = httpx.Client
    class _Patch:
        def __init__(self, *a, **kw):
            self._c = original_client(transport=transport)
        def __enter__(self): return self._c
        def __exit__(self, *a): self._c.close()

    with patch("newsbrief.sources.rss.httpx.Client", _Patch):
        p = RSSProvider()
        articles = list(p.fetch({"url": "https://example.com/feed", "category": "world"}, limit=10))

    assert len(articles) == 2
    assert articles[0].title == "First Headline"
    assert articles[0].url == "https://example.com/first"
    assert "Snippet one." in articles[0].snippet
    assert articles[0].source == "rss:example.com"
    assert articles[0].category == "world"
    assert articles[0].published_at is not None


def test_rss_fetch_network_error_returns_empty():
    def handler(request):
        raise httpx.ConnectError("boom")
    transport = httpx.MockTransport(handler)

    original_client = httpx.Client
    class _Patch:
        def __init__(self, *a, **kw):
            self._c = original_client(transport=transport)
        def __enter__(self): return self._c
        def __exit__(self, *a): self._c.close()

    with patch("newsbrief.sources.rss.httpx.Client", _Patch):
        p = RSSProvider()
        assert list(p.fetch({"url": "https://example.com/feed"})) == []
