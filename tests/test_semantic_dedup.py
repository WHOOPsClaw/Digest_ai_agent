"""Tests for Phase 6 — semantic dedup, entity grouping, stories tracking."""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from dataclasses import dataclass, field
from typing import List, Optional

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from newsbrief.processing.semantic_dedup import (
    compute_card_signature,
    extract_entities,
    entity_overlap,
    group_by_entities,
    filter_recent_duplicates,
    find_similar_in_history,
)


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------

@dataclass
class _Article:
    title: str = ""
    url: str = ""
    snippet: str = ""
    source: str = "rss:test"
    published_at: Optional[object] = None
    role: str = "source"


@dataclass
class _Event:
    canonical_title: str = ""
    articles: List[_Article] = field(default_factory=list)
    sources: List[dict] = field(default_factory=list)
    entities: Optional[dict] = None


class _FakeStorage:
    """In-memory SQLite-backed storage mirroring StorageAdapter API."""

    def __init__(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row

    def _sql(self, s):
        return s.replace("%s", "?")

    def execute(self, sql, params=()):
        self.conn.execute(self._sql(sql), params)
        self.conn.commit()

    def fetchall(self, sql, params=()):
        cur = self.conn.execute(self._sql(sql), params)
        return [dict(r) for r in cur.fetchall()]

    def fetchone(self, sql, params=()):
        cur = self.conn.execute(self._sql(sql), params)
        r = cur.fetchone()
        return dict(r) if r else None


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestCardSignature:
    def test_basic(self):
        sig = compute_card_signature({"title": "Tesla Cybertruck sales drop"})
        assert "tesla" in sig
        assert "cybertruck" in sig
        assert "the" not in sig.split()  # stopword removed

    def test_empty(self):
        assert compute_card_signature({"title": ""}) == ""


class TestEntityExtractionRegex:
    def test_tesla_cybertruck(self):
        ents = extract_entities("Tesla Cybertruck sales drop in Q1")
        orgs_lower = [o.lower() for o in ents["organizations"]]
        assert any("tesla" in o for o in orgs_lower)

    def test_product_with_version(self):
        ents = extract_entities("OpenAI releases GPT-5 for enterprise")
        products_lower = " ".join(ents["products"]).lower()
        orgs_lower = " ".join(ents["organizations"]).lower()
        assert "gpt" in products_lower or "gpt" in orgs_lower
        assert "openai" in orgs_lower

    def test_returns_all_keys(self):
        ents = extract_entities("Microsoft unveils Copilot upgrade")
        for key in ("organizations", "people", "products", "topics"):
            assert key in ents
            assert isinstance(ents[key], list)

    def test_empty_input(self):
        ents = extract_entities("")
        assert ents == {
            "organizations": [], "people": [], "products": [], "topics": [],
        }


class TestEntityOverlap:
    def test_identical(self):
        e = {
            "organizations": ["Tesla"],
            "products":      ["Cybertruck"],
            "people":        [],
            "topics":        [],
        }
        assert entity_overlap(e, e) > 0.5

    def test_shared_org_and_product(self):
        e1 = extract_entities("Tesla Cybertruck sales drop sharply")
        e2 = extract_entities("Tesla Cybertruck recall announced today")
        assert entity_overlap(e1, e2) > 0.3

    def test_unrelated(self):
        e1 = extract_entities("Tesla Cybertruck sales drop")
        e2 = extract_entities("Apple iPhone 17 launch in September")
        assert entity_overlap(e1, e2) < 0.3

    def test_empty(self):
        empty = {"organizations": [], "products": [], "people": [], "topics": []}
        assert entity_overlap(empty, empty) == 0.0


class TestGroupByEntities:
    def test_three_tesla_events_merge(self):
        events = [
            _Event(canonical_title="Tesla Cybertruck recall announced",
                   articles=[_Article(title="Tesla Cybertruck recall announced", url="u1")]),
            _Event(canonical_title="Tesla Cybertruck sales drop in Q1",
                   articles=[_Article(title="Tesla Cybertruck sales drop in Q1", url="u2")]),
            _Event(canonical_title="Tesla Cybertruck owners complain",
                   articles=[_Article(title="Tesla Cybertruck owners complain", url="u3")]),
            _Event(canonical_title="Apple Vision Pro 2 launches soon",
                   articles=[_Article(title="Apple Vision Pro 2 launches soon", url="u4")]),
        ]
        merged = group_by_entities(events, threshold=0.3)
        # Expect the 3 Tesla events collapsed into 1 merged group + 1 Apple.
        assert len(merged) == 2
        biggest = max(merged, key=lambda e: len(e.articles))
        assert len(biggest.articles) == 3

    def test_empty(self):
        assert group_by_entities([]) == []


class TestFilterRecentDuplicates:
    def _seed_digest_items(self, storage, titles_by_date):
        storage.execute(
            "CREATE TABLE digest_items ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "digest_date DATE, "
            "canonical_title TEXT, "
            "url_hash TEXT)"
        )
        for dd, titles in titles_by_date.items():
            for t in titles:
                storage.execute(
                    "INSERT INTO digest_items (digest_date, canonical_title, url_hash) "
                    "VALUES (%s, %s, %s)",
                    (dd, t, "h"),
                )

    def test_similar_title_dropped(self):
        from datetime import date, timedelta
        storage = _FakeStorage()
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        self._seed_digest_items(storage, {
            yesterday: ["Tesla Cybertruck sales drop sharply in Q1"],
        })
        events = [
            _Event(canonical_title="Tesla Cybertruck sales drop sharply in Q1",
                   articles=[_Article()]),
            _Event(canonical_title="Apple announces new MacBook Pro lineup",
                   articles=[_Article()]),
        ]
        kept = filter_recent_duplicates(events, storage, days=7, threshold=0.5)
        titles = [e.canonical_title for e in kept]
        assert "Apple announces new MacBook Pro lineup" in titles
        assert "Tesla Cybertruck sales drop sharply in Q1" not in titles

    def test_empty_history_passes_all(self):
        storage = _FakeStorage()
        events = [_Event(canonical_title="Anything", articles=[_Article()])]
        assert len(filter_recent_duplicates(events, storage)) == 1


class TestFindSimilarInHistory:
    def test_find(self):
        from datetime import date, timedelta
        storage = _FakeStorage()
        storage.execute(
            "CREATE TABLE digest_items ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "digest_date DATE, canonical_title TEXT, url_hash TEXT)"
        )
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        storage.execute(
            "INSERT INTO digest_items (digest_date, canonical_title, url_hash) "
            "VALUES (%s, %s, %s)",
            (yesterday, "Tesla Cybertruck sales drop in Q1", "h1"),
        )
        sig = compute_card_signature({"title": "Tesla Cybertruck sales drop in Q1"})
        matches = find_similar_in_history(sig, storage, days=7, threshold=0.3)
        assert matches
        assert matches[0][0] == yesterday


class TestStoriesTracking:
    def test_create_and_update(self):
        from newsbrief.core.stories import (
            ensure_stories_table, create_story, find_matching_story,
            update_story, was_in_recent_digest,
        )
        storage = _FakeStorage()
        ensure_stories_table(storage)

        ents = {"organizations": ["Tesla"], "products": ["Cybertruck"],
                "people": [], "topics": ["sales"]}
        sid = create_story("Tesla Cybertruck sales drop", ents, digest_id=1, storage=storage)
        assert sid is not None and sid > 0

        # Matching same entities must return the same story id.
        sid2 = find_matching_story(ents, storage, days=30, threshold=0.3)
        assert sid2 == sid

        update_story(sid, digest_id=2, storage=storage)
        row = storage.fetchone("SELECT card_count, digest_ids_json FROM stories WHERE id=%s", (sid,))
        assert row["card_count"] == 2
        assert "2" in row["digest_ids_json"]

        # Recent digest window.
        assert was_in_recent_digest(sid, days=7, storage=storage) is True

    def test_no_match_for_unrelated(self):
        from newsbrief.core.stories import (
            ensure_stories_table, create_story, find_matching_story,
        )
        storage = _FakeStorage()
        ensure_stories_table(storage)
        create_story(
            "Tesla Cybertruck sales drop",
            {"organizations": ["Tesla"], "products": ["Cybertruck"],
             "people": [], "topics": []},
            digest_id=1, storage=storage,
        )
        unrelated = {"organizations": ["Apple"], "products": ["Vision Pro"],
                     "people": [], "topics": []}
        assert find_matching_story(unrelated, storage, days=30, threshold=0.5) is None
