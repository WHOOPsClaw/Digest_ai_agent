"""Tests for newsbrief.utils.image_extractor."""
from __future__ import annotations

from types import SimpleNamespace

from newsbrief.utils.image_extractor import (
    extract_image_from_feedparser_entry,
    extract_image_from_html,
    extract_image_from_reddit,
    is_valid_image_url,
)


def test_is_valid_image_url_accepts_jpeg():
    assert is_valid_image_url("https://example.com/foo.jpg")
    assert is_valid_image_url("https://example.com/foo.png?x=1")
    assert is_valid_image_url("https://cdn.site.com/wp-content/uploads/2024/pic.jpg")


def test_is_valid_image_url_rejects_invalid():
    assert not is_valid_image_url(None)
    assert not is_valid_image_url("")
    assert not is_valid_image_url("ftp://example.com/foo.jpg")
    assert not is_valid_image_url("https://example.com/page.html")


def test_extract_from_feedparser_with_media_thumbnail():
    entry = SimpleNamespace(
        media_thumbnail=[{"url": "https://cdn.example.com/thumb.jpg"}],
    )
    assert extract_image_from_feedparser_entry(entry) == "https://cdn.example.com/thumb.jpg"


def test_extract_from_feedparser_with_media_content():
    entry = SimpleNamespace(
        media_content=[{"url": "https://cdn.example.com/pic.png", "medium": "image"}],
    )
    assert extract_image_from_feedparser_entry(entry) == "https://cdn.example.com/pic.png"


def test_extract_from_feedparser_from_summary_img():
    html = '<p>Hello <img src="https://cdn.example.com/inline.jpg" /> world</p>'
    entry = SimpleNamespace(summary=html)
    assert extract_image_from_feedparser_entry(entry) == "https://cdn.example.com/inline.jpg"


def test_extract_from_feedparser_empty():
    entry = SimpleNamespace()
    assert extract_image_from_feedparser_entry(entry) is None


def test_extract_from_reddit_preview():
    post = {
        "preview": {
            "images": [
                {"source": {"url": "https://i.redd.it/abc.jpg?amp;s=xyz"}}
            ]
        },
        "thumbnail": "default",
        "url": "https://reddit.com/r/foo/comments/xyz",
    }
    out = extract_image_from_reddit(post)
    assert out is not None
    assert out.startswith("https://i.redd.it/abc.jpg")
    assert "&amp;" not in out


def test_extract_from_reddit_direct_image_url():
    post = {"url": "https://i.imgur.com/abcd.png", "thumbnail": "default"}
    assert extract_image_from_reddit(post) == "https://i.imgur.com/abcd.png"


def test_extract_from_reddit_no_image():
    post = {"url": "https://news.ycombinator.com/item?id=1", "thumbnail": "default"}
    assert extract_image_from_reddit(post) is None


def test_extract_from_html_og_image():
    html = (
        '<html><head>'
        '<meta property="og:image" content="https://example.com/og.jpg">'
        '</head><body><img src="https://example.com/body.png"></body></html>'
    )
    assert extract_image_from_html(html) == "https://example.com/og.jpg"


def test_extract_from_html_fallback_img():
    html = '<html><body><img src="https://example.com/first.png"></body></html>'
    assert extract_image_from_html(html) == "https://example.com/first.png"


def test_extract_from_html_empty():
    assert extract_image_from_html("") is None
    assert extract_image_from_html("<html></html>") is None
