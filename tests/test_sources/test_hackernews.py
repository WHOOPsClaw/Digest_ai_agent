"""Tests for HackerNewsProvider."""
from __future__ import annotations

import json
from unittest.mock import patch

import httpx

from newsbrief.sources.hackernews import HackerNewsProvider


def _make_transport():
    ids = [1, 2, 3]
    items = {
        1: {"id": 1, "title": "Great story", "url": "https://a.example/1", "score": 200, "time": 1712000000, "descendants": 10},
        2: {"id": 2, "title": "Low score", "url": "https://a.example/2", "score": 10, "time": 1712000100},
        3: {"id": 3, "title": "Ask HN: text only", "score": 500, "time": 1712000200},  # no url
    }

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "topstories" in url:
            return httpx.Response(200, json=ids)
        for i in ids:
            if f"/item/{i}.json" in url:
                return httpx.Response(200, json=items[i])
        return httpx.Response(404, text="nope")

    return httpx.MockTransport(handler)


def test_hn_validate_config():
    p = HackerNewsProvider()
    assert p.validate_config({"type": "bogus"})[0].startswith("type must be")
    assert p.validate_config({"type": "top", "min_score": -1})[0].startswith("min_score")
    assert p.validate_config({}) == []


def test_hn_fetch_filters_score_and_missing_url():
    transport = _make_transport()

    original_client = httpx.Client
    class _Patch:
        def __init__(self, *a, **kw):
            self._c = original_client(transport=transport)
        def __enter__(self): return self._c
        def __exit__(self, *a): self._c.close()

    with patch("newsbrief.sources.hackernews.httpx.Client", _Patch):
        p = HackerNewsProvider()
        arts = list(p.fetch({"type": "top", "min_score": 50, "category": "tech"}))

    assert len(arts) == 1
    assert arts[0].title == "Great story"
    assert arts[0].source == "hackernews"
    assert arts[0].url == "https://a.example/1"
