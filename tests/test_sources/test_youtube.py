"""Tests for YouTubeProvider."""
from __future__ import annotations

from unittest.mock import patch

import httpx

from newsbrief.sources.youtube import YouTubeProvider

_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015"
      xmlns:media="http://search.yahoo.com/mrss/"
      xmlns="http://www.w3.org/2005/Atom">
  <title>Test Channel</title>
  <entry>
    <id>yt:video:abc123</id>
    <title>Video One</title>
    <link href="https://www.youtube.com/watch?v=abc123"/>
    <published>2025-04-01T10:00:00+00:00</published>
    <media:group>
      <media:description>Description of video one.</media:description>
    </media:group>
  </entry>
  <entry>
    <id>yt:video:def456</id>
    <title>Video Two</title>
    <link href="https://www.youtube.com/watch?v=def456"/>
    <published>2025-04-02T11:00:00+00:00</published>
    <media:group>
      <media:description>Second description.</media:description>
    </media:group>
  </entry>
</feed>
"""


def test_yt_validate_config():
    p = YouTubeProvider()
    assert p.validate_config({})[0].startswith("either channel_id")
    assert p.validate_config({"channel_id": "UCabc"}) == []


def test_yt_fetch_channel():
    def handler(request):
        return httpx.Response(200, text=_FEED, headers={"content-type": "application/xml"})
    transport = httpx.MockTransport(handler)

    original_client = httpx.Client
    class _Patch:
        def __init__(self, *a, **kw):
            self._c = original_client(transport=transport)
        def __enter__(self): return self._c
        def __exit__(self, *a): self._c.close()

    with patch("newsbrief.sources.youtube.httpx.Client", _Patch):
        p = YouTubeProvider()
        arts = list(p.fetch({"channel_id": "UCabcdefgh12345", "category": "tech"}, limit=10))

    assert len(arts) == 2
    assert arts[0].title == "Video One"
    assert arts[0].url.startswith("https://www.youtube.com/watch")
    assert arts[0].source == "youtube:UCabcdef"
    assert arts[0].category == "tech"
