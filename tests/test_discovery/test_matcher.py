"""Tests for discovery.matcher."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from newsbrief.discovery.matcher import match_interests
from newsbrief.llm.base import LLMResponse


KNOWN_SOURCES_PATH = Path(__file__).parent.parent.parent / "data" / "known_sources.yaml"


@pytest.fixture
def known_sources() -> dict:
    with open(KNOWN_SOURCES_PATH) as f:
        return yaml.safe_load(f)


class FakeRouter:
    def __init__(self, text: str):
        self._text = text
        self.prompts: list[str] = []

    def generate(self, prompt: str, task: str = "synthesis", **kwargs) -> LLMResponse:
        self.prompts.append(prompt)
        return LLMResponse(text=self._text, model="fake", latency_ms=1)


def test_match_interests_returns_topic_from_llm_json(known_sources):
    router = FakeRouter(
        '{"topics":[{"topic_id":"ai_ml","reasoning":"user likes LLMs"}]}'
    )
    result = match_interests("AI and coding agents", router, known_sources)
    assert len(result) == 1
    assert result[0]["topic_id"] == "ai_ml"
    assert result[0]["reasoning"] == "user likes LLMs"
    assert result[0]["display_name"]
    assert result[0]["emoji"]
    assert len(result[0]["sources"]) > 0
    # Prompt must mention available topics.
    assert "ai_ml" in router.prompts[0]
    assert "AI and coding agents" in router.prompts[0]


def test_match_interests_recommended_sources_ranked_first(known_sources):
    router = FakeRouter('{"topics":[{"topic_id":"tech","reasoning":"x"}]}')
    result = match_interests("tech startups", router, known_sources)
    srcs = result[0]["sources"]
    # Recommended sources appear before non-recommended ones.
    rec_flags = [s["recommended"] for s in srcs]
    # All True values precede all False values.
    if True in rec_flags and False in rec_flags:
        last_true = max(i for i, v in enumerate(rec_flags) if v)
        first_false = min(i for i, v in enumerate(rec_flags) if not v)
        assert last_true < first_false


def test_match_interests_fallback_to_keywords_on_bad_json(known_sources):
    router = FakeRouter("not json at all")
    result = match_interests("gaming video games", router, known_sources)
    # Should still return gaming topic via keyword fallback.
    ids = [r["topic_id"] for r in result]
    assert "gaming" in ids


def test_match_interests_handles_llm_exception(known_sources):
    class BoomRouter:
        def generate(self, *a, **k):
            raise RuntimeError("no key")

    result = match_interests("russia moscow", BoomRouter(), known_sources)
    ids = [r["topic_id"] for r in result]
    assert "russia" in ids


def test_match_interests_ignores_unknown_topic_ids(known_sources):
    router = FakeRouter(
        '{"topics":[{"topic_id":"nonexistent","reasoning":"x"},'
        '{"topic_id":"ai_ml","reasoning":"y"}]}'
    )
    result = match_interests("ai", router, known_sources)
    ids = [r["topic_id"] for r in result]
    assert "nonexistent" not in ids
    assert "ai_ml" in ids
