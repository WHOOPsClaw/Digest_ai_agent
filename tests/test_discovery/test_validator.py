"""Tests for discovery.validator."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from unittest.mock import MagicMock, patch

from newsbrief.discovery.validator import validate_source


def _rss_with_recent_entry() -> str:
    now = datetime.now(timezone.utc)
    pub = format_datetime(now - timedelta(days=1))
    return f"""<?xml version="1.0"?>
<rss version="2.0"><channel>
<title>x</title><link>http://x</link><description>d</description>
<item><title>t</title><link>http://x/1</link><pubDate>{pub}</pubDate></item>
</channel></rss>"""


def _rss_empty() -> str:
    return """<?xml version="1.0"?>
<rss version="2.0"><channel>
<title>x</title><link>http://x</link><description>d</description>
</channel></rss>"""


def _mock_client(status: int, text: str):
    resp = MagicMock()
    resp.status_code = status
    resp.text = text
    resp.raise_for_status = MagicMock()
    if status >= 400:
        resp.raise_for_status.side_effect = Exception(f"http {status}")
    resp.json = MagicMock(return_value={})
    resp.url = "http://x"
    client = MagicMock()
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    client.get = MagicMock(return_value=resp)
    client.head = MagicMock(return_value=resp)
    return client, resp


def test_validate_rss_live_feed():
    client, _ = _mock_client(200, _rss_with_recent_entry())
    with patch("newsbrief.discovery.validator.httpx.Client", return_value=client):
        res = validate_source({"type": "rss", "url": "http://example.com/feed"})
    assert res["valid"] is True
    assert res["items_recent"] >= 1


def test_validate_rss_empty_feed():
    client, _ = _mock_client(200, _rss_empty())
    with patch("newsbrief.discovery.validator.httpx.Client", return_value=client):
        res = validate_source({"type": "rss", "url": "http://example.com/feed"})
    assert res["valid"] is False
    assert "no entries" in res["error"]


def test_validate_rss_missing_url():
    res = validate_source({"type": "rss"})
    assert res["valid"] is False


def test_validate_hackernews_always_valid():
    res = validate_source({"type": "hackernews", "config": {"type": "top"}})
    assert res["valid"] is True


def test_validate_reddit_ok():
    resp = MagicMock()
    resp.status_code = 200
    resp.json = MagicMock(return_value={"data": {"subscribers": 100}})
    client = MagicMock()
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    client.get = MagicMock(return_value=resp)
    with patch("newsbrief.discovery.validator.httpx.Client", return_value=client):
        res = validate_source({"type": "reddit", "config": {"sub": "test"}})
    assert res["valid"] is True


def test_validate_reddit_404():
    resp = MagicMock()
    resp.status_code = 404
    client = MagicMock()
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    client.get = MagicMock(return_value=resp)
    with patch("newsbrief.discovery.validator.httpx.Client", return_value=client):
        res = validate_source({"type": "reddit", "config": {"sub": "test"}})
    assert res["valid"] is False


def test_validate_telegram_ok():
    html = "<html><body>" + "tgme_widget_message " * 3 + "</body></html>"
    resp = MagicMock()
    resp.status_code = 200
    resp.text = html
    client = MagicMock()
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    client.get = MagicMock(return_value=resp)
    with patch("newsbrief.discovery.validator.httpx.Client", return_value=client):
        res = validate_source({"type": "telegram", "config": {"username": "foo"}})
    assert res["valid"] is True
    assert res["items_recent"] >= 1


def test_validate_unknown_type():
    res = validate_source({"type": "weird"})
    assert res["valid"] is False
    assert "unknown type" in res["error"]
