"""Tests for feedback.collector."""
from __future__ import annotations

from newsbrief.feedback.collector import (
    get_feedback_stats,
    get_source_score,
    record_feedback,
)

from .conftest import insert_feedback


def test_record_feedback_writes_row(storage):
    record_feedback(storage, digest_id=1, article_idx=0, action="up", user_id="u1", source="rss:foo")
    rows = storage.fetchall("SELECT source, rating, user_id FROM feedback")
    assert len(rows) == 1
    assert rows[0]["rating"] == "up"
    assert rows[0]["source"] == "rss:foo"


def test_stats_aggregate_and_normalize(storage):
    insert_feedback(storage, "bbc", "up", n=3)
    insert_feedback(storage, "bbc", "down", n=1)
    insert_feedback(storage, "tabloid", "mute", n=2)   # normalizes to blocked
    insert_feedback(storage, "tabloid", "down", n=1)
    insert_feedback(storage, "niche", "save", n=1)     # normalizes to saved

    stats = get_feedback_stats(storage, days=30)
    ratings = stats["source_ratings"]

    assert ratings["bbc"]["up"] == 3
    assert ratings["bbc"]["down"] == 1
    assert ratings["tabloid"]["blocked"] == 2
    assert ratings["niche"]["saved"] == 1

    # bbc score: (3 - 1)/4 = 0.5
    assert ratings["bbc"]["score"] == 0.5
    # tabloid score: (0 - 1 - 2*2)/3 = -1.6666 clamped to -1
    assert ratings["tabloid"]["score"] == -1.0

    assert "bbc" in stats["top_sources"]
    assert "tabloid" in stats["bottom_sources"]


def test_source_score_empty_returns_zero(storage):
    assert get_source_score(storage, "nope") == 0.0


def test_source_score_single(storage):
    insert_feedback(storage, "x", "up", n=2)
    insert_feedback(storage, "x", "down", n=1)
    # (2 - 1)/3 = 0.3333
    assert round(get_source_score(storage, "x"), 2) == 0.33
