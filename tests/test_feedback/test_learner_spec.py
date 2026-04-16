"""Tests for suggest_adjustments / apply_learning_suggestions."""
from __future__ import annotations

from newsbrief.config import NewsbriefConfig, TopicConfig
from newsbrief.feedback.learner import (
    suggest_adjustments,
    apply_learning_suggestions,
)

from .conftest import insert_feedback


def test_suggest_adjustments_basic(storage):
    # Positive source
    insert_feedback(storage, "simon.net", "up", n=8)
    insert_feedback(storage, "simon.net", "down", n=1)
    # Mute-heavy source → remove candidate
    insert_feedback(storage, "spam.io", "mute", n=4)

    cfg = NewsbriefConfig()
    s = suggest_adjustments(storage, cfg, days=30)
    assert "simon.net" in s["source_boosts"]
    assert s["source_boosts"]["simon.net"] >= 0.2
    assert s["source_boosts"]["simon.net"] <= 0.5
    assert "spam.io" in s["remove_sources"]
    assert s["reasoning"]


def test_apply_learning_suggestions_mutates_config(storage):
    cfg = NewsbriefConfig(
        topics=[
            TopicConfig(
                id="t1",
                name="Test",
                sources={"bad.io": {"url": "x"}, "good.io": {"url": "y"}},
                blacklist=["existing"],
            ),
        ],
    )
    suggestions = {
        "source_boosts":    {"good.io": 0.3},
        "add_to_blacklist": ["spam", "clickbait"],
        "remove_sources":   ["bad.io"],
        "reasoning":        "test",
    }
    out = apply_learning_suggestions(cfg, suggestions)
    # Boosts stashed
    assert getattr(out, "_source_boosts", {}).get("good.io") == 0.3
    # Blacklist merged
    assert "existing" in out.topics[0].blacklist
    assert "spam" in out.topics[0].blacklist
    assert "clickbait" in out.topics[0].blacklist
    # Removed source dropped
    assert "bad.io" not in out.topics[0].sources
    assert "good.io" in out.topics[0].sources


def test_suggest_no_data_returns_empty(storage):
    cfg = NewsbriefConfig()
    s = suggest_adjustments(storage, cfg, days=30)
    assert s["source_boosts"] == {}
    assert s["remove_sources"] == []
