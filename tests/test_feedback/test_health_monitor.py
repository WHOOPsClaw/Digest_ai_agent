"""Tests for feedback.health_monitor."""
from __future__ import annotations

import pytest

from newsbrief.config import NewsbriefConfig, TopicConfig
from newsbrief.feedback.health_monitor import (
    check_source_health,
    monitor_all_sources,
    notify_dead_sources,
)


@pytest.fixture
def articles_storage(tmp_path, monkeypatch):
    db_path = tmp_path / "art.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    import newsbrief.core.storage as st_mod
    st_mod._storage = None
    adapter = st_mod.StorageAdapter()
    adapter.ensure_schema()
    return adapter


def _insert_article(storage, source: str, n: int = 1) -> None:
    for i in range(n):
        storage.execute(
            "INSERT INTO articles (url, url_hash, title, snippet, category, source) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (f"https://{source}/{i}", f"h{source}{i}", f"title{i}", "", "world", source),
        )


def test_dead_source_when_no_items(articles_storage):
    rec = check_source_health({"source": "ghost.io"}, articles_storage, days=14)
    assert rec["healthy"] is False
    assert rec["items_count"] == 0


def test_healthy_source_above_threshold(articles_storage):
    _insert_article(articles_storage, "alive.com", n=5)
    rec = check_source_health({"source": "alive.com"}, articles_storage, days=14)
    assert rec["healthy"] is True
    assert rec["items_count"] == 5


def test_unhealthy_below_min(articles_storage):
    _insert_article(articles_storage, "slow.io", n=2)
    rec = check_source_health({"source": "slow.io"}, articles_storage, days=14)
    assert rec["healthy"] is False
    assert rec["items_count"] == 2


def test_monitor_all_sources(articles_storage):
    _insert_article(articles_storage, "alive.com", n=5)
    cfg = NewsbriefConfig(topics=[
        TopicConfig(
            id="t", name="T",
            sources={
                "rss": [{"id": "alive.com", "url": "https://alive.com/feed"}],
                "tg":  [{"id": "dead_channel", "url": "https://t.me/dead"}],
            },
        ),
    ])
    bad = monitor_all_sources(cfg, articles_storage, days=14)
    keys = [b["source"] for b in bad]
    assert "dead_channel" in keys
    assert "alive.com" not in keys


def test_notify_dead_sources_uses_channel():
    captured: list[str] = []

    class FakeChannel:
        def send_message(self, text: str) -> None:
            captured.append(text)

    notify_dead_sources([{"source": "x", "reason": "0 items"}], FakeChannel())
    assert captured
    assert "Dead sources" in captured[0]
    assert "x" in captured[0]


def test_notify_dead_sources_empty_noop():
    class FakeChannel:
        def send_message(self, text: str) -> None:
            raise AssertionError("should not be called")
    notify_dead_sources([], FakeChannel())
