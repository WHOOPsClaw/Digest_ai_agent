"""Tests for TelegramProvider."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import httpx

from newsbrief.sources.telegram import TelegramProvider

FIXTURE = Path(__file__).parent.parent / "fixtures" / "telegram_channel.html"


def _mock(body: str, status: int = 200):
    def handler(request):
        return httpx.Response(status, text=body)
    return httpx.MockTransport(handler)


def test_tg_validate_username():
    p = TelegramProvider()
    assert p.validate_config({}) == ["username is required"]
    assert p.validate_config({"username": "!!"}) == ["invalid telegram username: !!"]
    assert p.validate_config({"username": "good_channel"}) == []


def test_tg_fetch_parses_messages():
    body = FIXTURE.read_text()
    transport = _mock(body)

    original_client = httpx.Client
    class _Patch:
        def __init__(self, *a, **kw):
            self._c = original_client(transport=transport)
        def __enter__(self): return self._c
        def __exit__(self, *a): self._c.close()

    with patch("newsbrief.sources.telegram.httpx.Client", _Patch):
        p = TelegramProvider()
        articles = list(p.fetch({"username": "testchannel", "category": "tech"}, limit=10))

    assert len(articles) == 3
    assert articles[0].source == "tg:testchannel"
    assert articles[0].role == "signal"
    assert articles[0].url == "https://t.me/testchannel/101"
    assert articles[0].published_at is not None
    assert articles[0].category == "tech"
    assert "first test post" in articles[0].snippet


def test_tg_fetch_bad_status_returns_empty():
    transport = _mock("nope", status=404)

    original_client = httpx.Client
    class _Patch:
        def __init__(self, *a, **kw):
            self._c = original_client(transport=transport)
        def __enter__(self): return self._c
        def __exit__(self, *a): self._c.close()

    with patch("newsbrief.sources.telegram.httpx.Client", _Patch):
        p = TelegramProvider()
        assert list(p.fetch({"username": "testchannel"})) == []
