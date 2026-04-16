"""Tests for the spec-shaped collector API (get_source_ratings / top / blocked / user)."""
from __future__ import annotations

import pytest

from newsbrief.feedback.collector import (
    get_source_ratings,
    get_top_sources,
    get_blocked_sources,
    get_user_feedback_stats,
)

from .conftest import insert_feedback


def test_source_ratings_empty(storage):
    assert get_source_ratings(storage) == {}


def test_source_ratings_shape_and_sort(storage):
    insert_feedback(storage, "good.com", "up", n=5)
    insert_feedback(storage, "good.com", "down", n=1)
    insert_feedback(storage, "bad.com", "mute", n=3)
    insert_feedback(storage, "neu.com", "save", n=1)

    r = get_source_ratings(storage)
    # Shape check
    for bucket in r.values():
        for k in ("up", "down", "block", "save", "total", "score"):
            assert k in bucket

    # good.com: (5 - 1 - 0)/6 ≈ 0.667
    assert r["good.com"]["score"] == pytest.approx(4 / 6, rel=1e-3)
    # bad.com: (0 - 0 - 6)/3 = -2.0
    assert r["bad.com"]["score"] == pytest.approx(-2.0, rel=1e-3)

    keys = list(r.keys())
    assert keys[0] in {"neu.com", "good.com"}  # positives first
    assert keys[-1] == "bad.com"


def test_top_sources_filters_by_min_and_score(storage):
    # Too few signals
    insert_feedback(storage, "small.com", "up", n=4)
    assert get_top_sources(storage, min_feedback=5) == []

    # Enough signals, strong positive
    insert_feedback(storage, "big.com", "up", n=10)
    tops = get_top_sources(storage, min_feedback=5)
    assert any(t["source"] == "big.com" for t in tops)
    assert tops[0]["score"] > 0.5


def test_blocked_sources(storage):
    insert_feedback(storage, "spam.io", "mute", n=2)
    assert get_blocked_sources(storage, threshold=3) == []
    insert_feedback(storage, "spam.io", "mute", n=1)
    assert get_blocked_sources(storage, threshold=3) == ["spam.io"]


def test_user_feedback_stats(storage):
    insert_feedback(storage, "a.com", "up", n=1, user_id="alice")
    insert_feedback(storage, "a.com", "down", n=1, user_id="alice")
    insert_feedback(storage, "a.com", "save", n=1, user_id="alice")
    insert_feedback(storage, "a.com", "up", n=5, user_id="bob")

    s = get_user_feedback_stats(storage, "alice", days=7)
    assert s == {"up": 1, "down": 1, "block": 0, "save": 1, "total": 3, "period_days": 7}
