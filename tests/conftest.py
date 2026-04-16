"""conftest.py — shared fixtures for digest tests."""
import pytest
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import List, Optional


@dataclass
class FakeSynthesizedItem:
    """Minimal stub matching SynthesizedItem interface for composer/service tests."""
    title:           str = "Test Title"
    summary_ru:      str = "Краткое описание события."
    why_it_matters:  str = "Это важно потому что..."
    editor_take:     str = ""
    sources:         list = field(default_factory=lambda: [
        {"url": "https://example.com/1", "source": "rss"},
        {"url": "https://example.com/2", "source": "search"},
    ])
    category:        str = "world"
    llm_used:        bool = True
    final_score:     float = 0.5
    confidence:      str = "verified"
    impact_zones:    str = ""
    canonical_title: str = ""

    def __post_init__(self):
        if not self.canonical_title:
            self.canonical_title = self.title


@dataclass
class FakeRawArticle:
    """Minimal stub for RawArticle."""
    category:     str = "world"
    title:        str = "Article Title"
    url:          str = "https://example.com"
    snippet:      str = "Some snippet text"
    source:       str = "rss:test"
    published_at: Optional[datetime] = None
    role:         str = "source"


@dataclass
class FakeEvent:
    """Minimal stub for DigestEvent."""
    canonical_title: str = "Event Title"
    articles:        list = field(default_factory=list)

    def __post_init__(self):
        if not self.articles:
            self.articles = [FakeRawArticle(title=self.canonical_title)]


def make_items(n: int, category: str = "world", title_prefix: str = "News") -> List[FakeSynthesizedItem]:
    """Create n fake synthesized items for testing."""
    return [
        FakeSynthesizedItem(
            title=f"{title_prefix} {i+1}",
            summary_ru=f"Описание новости {i+1}. " * 10,
            category=category,
            final_score=1.0 - i * 0.1,
        )
        for i in range(n)
    ]
