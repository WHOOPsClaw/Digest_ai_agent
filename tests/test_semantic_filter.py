"""Tests for processing.semantic_filter."""
from __future__ import annotations

from dataclasses import dataclass

from newsbrief.processing.semantic_filter import (
    build_filter_prompt,
    filter_events_semantically,
)


@dataclass
class FakeEv:
    canonical_title: str
    articles: list = None


@dataclass
class FakeResp:
    text: str
    prompt_tokens: int = 50
    completion_tokens: int = 10


class FakeRouter:
    """Captures calls; returns canned text per batch."""

    def __init__(self, responses: list[str]):
        self.responses = list(responses)
        self.calls: list[str] = []

    def generate(self, prompt: str, task: str = "filter"):
        self.calls.append(prompt)
        text = self.responses.pop(0) if self.responses else '{"keep_indices": []}'
        return FakeResp(text=text)


def _mkevents(n: int) -> list:
    return [FakeEv(canonical_title=f"Title {i}") for i in range(n)]


def test_build_filter_prompt_contains_titles_and_criteria():
    items = [{"title": "AI news"}, {"title": "Sports recap"}]
    prompt = build_filter_prompt(items, include_criteria=["ai"], exclude_criteria=["sports"])
    assert "AI news" in prompt
    assert "Sports recap" in prompt
    assert "ai" in prompt.lower()
    assert "sports" in prompt.lower()
    assert "keep_indices" in prompt


def test_batching_10_per_call():
    events = _mkevents(25)
    # All batches say "keep all"
    router = FakeRouter([
        '{"keep_indices": [0,1,2,3,4,5,6,7,8,9]}',
        '{"keep_indices": [0,1,2,3,4,5,6,7,8,9]}',
        '{"keep_indices": [0,1,2,3,4]}',
    ])
    out = filter_events_semantically(events, include=["x"], exclude=[], llm_router=router)
    assert len(router.calls) == 3
    assert len(out) == 25


def test_json_parsing_drops_excluded():
    events = _mkevents(3)
    router = FakeRouter(['{"keep_indices": [0, 2]}'])
    out = filter_events_semantically(events, include=[], exclude=["spam"], llm_router=router)
    titles = [e.canonical_title for e in out]
    assert titles == ["Title 0", "Title 2"]


def test_json_in_markdown_wrapper_still_parsed():
    events = _mkevents(2)
    router = FakeRouter(['```json\n{"keep_indices": [1]}\n```'])
    out = filter_events_semantically(events, include=[], exclude=["x"], llm_router=router)
    assert [e.canonical_title for e in out] == ["Title 1"]


def test_fail_open_on_llm_error():
    events = _mkevents(3)

    class Boom:
        def generate(self, *a, **kw):
            raise RuntimeError("LLM down")

    out = filter_events_semantically(events, include=["x"], exclude=[], llm_router=Boom())
    assert len(out) == 3


def test_fail_open_on_bad_json():
    events = _mkevents(2)
    router = FakeRouter(["not json at all"])
    out = filter_events_semantically(events, include=[], exclude=["x"], llm_router=router)
    assert len(out) == 2


def test_no_criteria_returns_unchanged():
    events = _mkevents(5)
    router = FakeRouter([])
    out = filter_events_semantically(events, include=[], exclude=[], llm_router=router)
    assert out == events
    assert router.calls == []


def test_no_router_returns_unchanged():
    events = _mkevents(4)
    out = filter_events_semantically(events, include=["x"], exclude=[], llm_router=None)
    assert out == events
