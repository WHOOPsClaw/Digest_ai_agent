"""Tests for processing.semantic_filter.filter_batch (article-level)."""
from __future__ import annotations

from dataclasses import dataclass

from newsbrief.config import NewsbriefConfig
from newsbrief.processing.semantic_filter import filter_batch


@dataclass
class Art:
    title: str
    snippet: str = ""


class FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class FakeRouter:
    """Records prompts and returns canned keep-indices."""

    def __init__(self, keep: list[int]):
        self._keep = keep
        self.prompts: list[str] = []
        self.tasks: list[str] = []

    def generate(self, prompt: str, task: str = "synthesis", **kw):
        self.prompts.append(prompt)
        self.tasks.append(task)
        import json
        return FakeResponse(json.dumps({"keep": self._keep}))


def test_filter_batch_keeps_only_indicated():
    arts = [Art(f"t{i}") for i in range(5)]
    router = FakeRouter(keep=[0, 2, 4])
    cfg = NewsbriefConfig()
    out = filter_batch(arts, cfg, router,
                       include_patterns=["ai"], exclude_patterns=["sports"])
    assert len(out) == 3
    assert out[0].title == "t0"
    assert out[1].title == "t2"
    assert out[2].title == "t4"
    assert router.tasks == ["filter"]
    assert "ai" in router.prompts[0]
    assert "sports" in router.prompts[0]


def test_filter_batch_empty_input():
    cfg = NewsbriefConfig()
    assert filter_batch([], cfg, FakeRouter(keep=[])) == []


def test_filter_batch_no_router_returns_all():
    cfg = NewsbriefConfig()
    arts = [Art("x"), Art("y")]
    out = filter_batch(arts, cfg, None, include_patterns=["ai"])
    assert len(out) == 2


def test_filter_batch_fails_open_on_bad_response():
    class BadRouter:
        def generate(self, prompt, task="synthesis", **kw):
            return FakeResponse("garbage not json")
    cfg = NewsbriefConfig()
    arts = [Art("a"), Art("b")]
    out = filter_batch(arts, cfg, BadRouter(), include_patterns=["x"])
    # Fails open: keeps all
    assert len(out) == 2


def test_filter_batch_batching_over_10():
    arts = [Art(f"t{i}") for i in range(15)]
    router = FakeRouter(keep=[0, 1])  # keep 2 per batch → 4 total
    cfg = NewsbriefConfig()
    out = filter_batch(arts, cfg, router, include_patterns=["x"])
    assert len(router.prompts) == 2     # two batches
    assert len(out) == 4
