"""Tests for RedditProvider."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import httpx

from newsbrief.sources.reddit import RedditProvider

FIXTURE = Path(__file__).parent.parent / "fixtures" / "reddit_hot.json"


def _mock(body: str):
    def handler(request):
        return httpx.Response(200, text=body, headers={"content-type": "application/json"})
    return httpx.MockTransport(handler)


def test_reddit_validate_config():
    p = RedditProvider()
    assert p.validate_config({}) == ["sub is required"]
    assert p.validate_config({"sub": "bad!"})[0].startswith("invalid subreddit")
    assert p.validate_config({"sub": "LocalLLaMA"}) == []


def test_reddit_fetch_filters_by_score():
    body = FIXTURE.read_text()
    transport = _mock(body)

    original_client = httpx.Client
    class _Patch:
        def __init__(self, *a, **kw):
            self._c = original_client(transport=transport)
        def __enter__(self): return self._c
        def __exit__(self, *a): self._c.close()

    with patch("newsbrief.sources.reddit.httpx.Client", _Patch):
        p = RedditProvider()
        arts = list(p.fetch({"sub": "test", "min_score": 100, "category": "tech"}))

    assert len(arts) == 2  # high + another good, low filtered out
    titles = [a.title for a in arts]
    assert "High score post" in titles
    assert "Another good post" in titles
    assert "Low score post" not in titles
    assert arts[0].source == "reddit:test"
    assert arts[0].published_at is not None
