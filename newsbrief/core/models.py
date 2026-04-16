"""Core pydantic models — Article, Event, Card, Digest."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as _date, datetime
from typing import Any, Literal, Optional


@dataclass
class RawArticle:
    """Raw article from a source before processing."""
    category:     str
    title:        str
    url:          str
    snippet:      str
    source:       str  # e.g. "rss:bbc_world", "tg:pekagame", "reddit:LocalLLaMA"
    published_at: Optional[datetime] = None
    role:         str = "source"  # "signal" | "source" | "analysis"
    image_url:    Optional[str] = None


@dataclass
class DigestEvent:
    """A group of similar articles (deduplicated)."""
    canonical_title: str
    articles:        list = field(default_factory=list)
    published_at:    Optional[datetime] = None


@dataclass
class SynthesizedItem:
    """AI-generated card ready for delivery."""
    title:           str
    summary_ru:      str
    why_it_matters:  str = ""
    sources:         list = field(default_factory=list)
    category:        str = ""
    llm_used:        bool = True
    final_score:     float = 0.0
    canonical_title: str = ""
    confidence:      Literal["verified", "partial", "signal"] = "verified"
    image_url:       Optional[str] = None

    def __post_init__(self):
        if not self.canonical_title:
            self.canonical_title = self.title


@dataclass
class DigestIssue:
    """Complete digest ready for delivery."""
    full_text:       str
    telegram_parts:  list[str]
    headline_items:  list[str] = field(default_factory=list)
    category_blocks: dict = field(default_factory=dict)
    item_count:      int = 0
    metadata:        dict = field(default_factory=dict)
