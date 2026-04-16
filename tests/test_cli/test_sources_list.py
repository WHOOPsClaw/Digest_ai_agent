"""Tests for `newsbrief sources list`."""
from __future__ import annotations

from io import StringIO

from rich.console import Console

from newsbrief.cli_sources import cmd_sources_list, iter_topic_sources
from newsbrief.config import NewsbriefConfig, TopicConfig


def _make_cfg() -> NewsbriefConfig:
    cfg = NewsbriefConfig()
    cfg.topics = [
        TopicConfig(
            id="ai_ml",
            name="AI and Agents",
            emoji="🤖",
            sources={
                "rss": [
                    "https://simonwillison.net/atom/everything/",
                    "https://huggingface.co/blog/feed.xml",
                ],
                "telegram": ["@neuraldvig"],
                "reddit": [{"subreddit": "LocalLLaMA", "min_score": 50}],
                "hackernews": True,
            },
        ),
        TopicConfig(
            id="world",
            name="World News",
            emoji="🌍",
            sources={"rss": ["https://example.com/feed"]},
        ),
    ]
    return cfg


def test_sources_list_shows_all_topics_and_sources():
    buf = StringIO()
    console = Console(file=buf, width=120, force_terminal=False)
    rc = cmd_sources_list(cfg=_make_cfg(), console=console)
    out = buf.getvalue()
    assert rc == 0
    # Topics
    assert "AI and Agents" in out
    assert "id=ai_ml" in out
    assert "World News" in out
    assert "id=world" in out
    # Sources
    assert "simonwillison.net" in out
    assert "@neuraldvig" in out
    assert "r/LocalLLaMA" in out
    assert "min_score=50" in out
    assert "HackerNews" in out
    # Summary
    assert "2 topics" in out


def test_iter_topic_sources_flattens_all_kinds():
    topic = TopicConfig(
        id="t", name="T",
        sources={
            "rss": ["https://a/"], "telegram": ["u1"],
            "reddit": [{"subreddit": "x"}], "hackernews": True,
            "youtube": ["UCxx"],
        },
    )
    items = iter_topic_sources(topic)
    types = sorted(i["type"] for i in items)
    assert types == ["hackernews", "reddit", "rss", "telegram", "youtube"]


def test_sources_list_handles_empty_config():
    buf = StringIO()
    console = Console(file=buf, width=120, force_terminal=False)
    cfg = NewsbriefConfig()
    rc = cmd_sources_list(cfg=cfg, console=console)
    assert rc == 0
    assert "0 topics" in buf.getvalue()
