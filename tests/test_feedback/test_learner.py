"""Tests for feedback.learner."""
from __future__ import annotations

from newsbrief.config import NewsbriefConfig
from newsbrief.feedback.learner import (
    apply_learning,
    auto_blacklist_candidates,
    compute_source_boosts,
)

from .conftest import insert_feedback


def test_boost_neutral_below_min_feedback(storage):
    insert_feedback(storage, "bbc", "up", n=3)  # below min_feedback=10
    cfg = NewsbriefConfig()
    boosts = compute_source_boosts(storage, cfg, min_feedback=10)
    assert boosts["bbc"] == 1.0


def test_boost_high_for_positive_score(storage):
    insert_feedback(storage, "bbc", "up", n=9)
    insert_feedback(storage, "bbc", "down", n=1)  # score 0.8
    cfg = NewsbriefConfig()
    boosts = compute_source_boosts(storage, cfg, min_feedback=5)
    assert boosts["bbc"] == 1.5


def test_boost_low_for_negative_score(storage):
    insert_feedback(storage, "tabloid", "down", n=8)
    insert_feedback(storage, "tabloid", "up", n=2)  # score -0.6
    cfg = NewsbriefConfig()
    boosts = compute_source_boosts(storage, cfg, min_feedback=5)
    assert boosts["tabloid"] == 0.5


def test_boost_neutral_for_mixed_score(storage):
    insert_feedback(storage, "mix", "up", n=5)
    insert_feedback(storage, "mix", "down", n=5)  # score 0.0
    cfg = NewsbriefConfig()
    boosts = compute_source_boosts(storage, cfg, min_feedback=5)
    assert boosts["mix"] == 1.0


def test_auto_blacklist_threshold(storage):
    insert_feedback(storage, "spam", "mute", n=3)
    insert_feedback(storage, "ok", "mute", n=1)
    candidates = auto_blacklist_candidates(storage, threshold=3)
    assert "spam" in candidates
    assert "ok" not in candidates


def test_apply_learning_report(storage):
    insert_feedback(storage, "good", "up", n=9)
    insert_feedback(storage, "good", "down", n=1)
    insert_feedback(storage, "bad", "down", n=8)
    insert_feedback(storage, "bad", "up", n=2)
    insert_feedback(storage, "spam", "mute", n=4)

    cfg = NewsbriefConfig()
    cfg.learning.min_feedback = 5
    cfg.learning.auto_blacklist_threshold = 3
    report = apply_learning(storage, cfg)

    assert "good" in report["boosted"]
    assert "bad" in report["demoted"]
    assert "spam" in report["auto_blacklisted"]
    assert report["boosts"]["good"] == 1.5
    assert report["boosts"]["bad"] == 0.5
