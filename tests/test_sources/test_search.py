"""Tests for SearchProvider."""
from __future__ import annotations

from unittest.mock import patch

import httpx

from newsbrief.sources.search import SearchProvider


_REAL_CLIENT = httpx.Client


def _patch_client(handler):
    transport = httpx.MockTransport(handler)

    class _P:
        def __init__(self, *a, **kw):
            self._c = _REAL_CLIENT(transport=transport)
        def __enter__(self): return self._c
        def __exit__(self, *a): self._c.close()

    return _P


def test_search_validate():
    p = SearchProvider()
    assert "query is required" in p.validate_config({})
    assert "base_url is required for searxng" in p.validate_config(
        {"query": "x", "engine": "searxng"}
    )
    assert "api_key is required for brave" in p.validate_config(
        {"query": "x", "engine": "brave"}
    )
    assert p.validate_config({"query": "x", "engine": "ddg"}) == []


def test_search_searxng():
    def handler(request):
        assert "/search" in str(request.url)
        return httpx.Response(200, json={
            "results": [
                {"url": "https://ex.com/a", "title": "A", "content": "snippet a"},
                {"url": "https://ex.com/b", "title": "B", "content": "snippet b"},
            ]
        })

    with patch("newsbrief.sources.search.httpx.Client", _patch_client(handler)):
        arts = list(SearchProvider().fetch(
            {"query": "foo", "engine": "searxng", "base_url": "https://sx.example"},
            limit=5,
        ))

    assert len(arts) == 2
    assert arts[0].role == "signal"
    assert arts[0].source == "search"
    assert arts[0].url == "https://ex.com/a"


def test_search_brave():
    def handler(request):
        assert request.headers.get("X-Subscription-Token") == "KEY"
        return httpx.Response(200, json={
            "web": {"results": [
                {"url": "https://b.example/1", "title": "<b>Brave</b>",
                 "description": "desc"},
            ]}
        })

    with patch("newsbrief.sources.search.httpx.Client", _patch_client(handler)):
        arts = list(SearchProvider().fetch(
            {"query": "foo", "engine": "brave", "api_key": "KEY"},
            limit=5,
        ))

    assert len(arts) == 1
    assert arts[0].title == "Brave"
    assert arts[0].url == "https://b.example/1"


def test_search_ddg_fallback():
    html = """
    <html><body>
      <div class="result">
        <a class="result__a" href="/l/?uddg=https%3A%2F%2Fddg.example%2Fone">First</a>
        <a class="result__snippet" href="#">Snippet one here</a>
      </div>
      <div class="result">
        <a class="result__a" href="https://ddg.example/two">Second</a>
        <a class="result__snippet" href="#">Snippet two</a>
      </div>
    </body></html>
    """
    def handler(request):
        return httpx.Response(200, text=html)

    with patch("newsbrief.sources.search.httpx.Client", _patch_client(handler)):
        arts = list(SearchProvider().fetch({"query": "foo", "engine": "ddg"}, limit=5))

    assert len(arts) == 2
    assert arts[0].url == "https://ddg.example/one"
    assert arts[0].title == "First"
    assert arts[1].url == "https://ddg.example/two"
