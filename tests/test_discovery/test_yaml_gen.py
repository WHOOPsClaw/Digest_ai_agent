"""Tests for discovery.yaml_gen."""
from __future__ import annotations

from newsbrief.config import TopicConfig
from newsbrief.discovery.yaml_gen import generate_topics_yaml, source_id


def _make_match() -> list[dict]:
    return [
        {
            "topic_id": "ai_ml",
            "display_name": "AI / Machine Learning",
            "emoji": "🤖",
            "reasoning": "r",
            "sources": [
                {
                    "source_ref": {
                        "type": "rss",
                        "url": "https://example.com/feed",
                        "name": "Ex",
                    },
                    "recommended": True,
                    "reason": "",
                },
                {
                    "source_ref": {
                        "type": "telegram",
                        "config": {"username": "foo"},
                        "name": "Foo",
                    },
                    "recommended": False,
                    "reason": "",
                },
                {
                    "source_ref": {
                        "type": "reddit",
                        "config": {"sub": "LocalLLaMA", "min_score": 50},
                        "name": "r/LocalLLaMA",
                    },
                    "recommended": True,
                    "reason": "",
                },
                {
                    "source_ref": {
                        "type": "hackernews",
                        "config": {"type": "top"},
                        "name": "HN",
                    },
                    "recommended": True,
                    "reason": "",
                },
            ],
        }
    ]


def test_generate_topics_yaml_shape():
    matched = _make_match()
    selected = {source_id(s["source_ref"]) for s in matched[0]["sources"]}
    topics = generate_topics_yaml(matched, selected)

    assert len(topics) == 1
    t = topics[0]
    assert t["id"] == "ai_ml"
    assert t["name"] == "AI / Machine Learning"
    assert t["emoji"] == "🤖"
    assert t["items_per_digest"] == 5

    srcs = t["sources"]
    assert srcs["rss"] == ["https://example.com/feed"]
    assert srcs["telegram"] == ["foo"]
    assert srcs["reddit"] == [{"sub": "LocalLLaMA", "min_score": 50}]
    assert srcs["hackernews"] is True


def test_generate_topics_yaml_filters_unselected():
    matched = _make_match()
    # Only pick the RSS one.
    selected = {"rss:https://example.com/feed"}
    topics = generate_topics_yaml(matched, selected)
    assert len(topics) == 1
    srcs = topics[0]["sources"]
    assert "rss" in srcs
    assert "telegram" not in srcs
    assert "reddit" not in srcs
    assert "hackernews" not in srcs


def test_generate_topics_yaml_empty_selection_drops_topic():
    matched = _make_match()
    topics = generate_topics_yaml(matched, set())
    assert topics == []


def test_generate_topics_yaml_output_validates_as_topicconfig():
    matched = _make_match()
    selected = {source_id(s["source_ref"]) for s in matched[0]["sources"]}
    topics = generate_topics_yaml(matched, selected)
    # Must be compatible with TopicConfig.
    validated = [TopicConfig.model_validate(t) for t in topics]
    assert validated[0].id == "ai_ml"
    assert validated[0].items_per_digest == 5
