"""Tests for digest/composer.py — split logic, section assembly, edge cases."""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from newsbrief.processing.composer import (
    split_digest_for_telegram,
    _sub_split_section,
    compose_headline_block,
    _compose_item_card,
    compose_digest_issue,
    TELEGRAM_MAX_LEN,
    _SECTION_SEP,
    _ITEM_SEP,
)
from conftest import FakeSynthesizedItem, make_items


class TestSplitDigestForTelegram:
    def test_empty_text(self):
        assert split_digest_for_telegram("") == []

    def test_single_short_section(self):
        parts = split_digest_for_telegram("Hello world")
        assert parts == ["Hello world"]

    def test_splits_on_triple_newline(self):
        text = "Section 1\n\n\nSection 2\n\n\nSection 3"
        parts = split_digest_for_telegram(text)
        assert len(parts) == 3
        assert parts[0] == "Section 1"
        assert parts[1] == "Section 2"
        assert parts[2] == "Section 3"

    def test_long_section_gets_sub_split(self):
        # Create a section longer than TELEGRAM_MAX_LEN with item separators
        items = [f"Item {i} content " * 50 for i in range(10)]
        long_section = _ITEM_SEP.join(items)
        assert len(long_section) > TELEGRAM_MAX_LEN
        parts = split_digest_for_telegram(long_section)
        assert len(parts) > 1
        for part in parts:
            assert len(part) <= TELEGRAM_MAX_LEN

    def test_preserves_all_content(self):
        sections = ["Short section 1", "Short section 2", "Short section 3"]
        text = _SECTION_SEP.join(sections)
        parts = split_digest_for_telegram(text)
        assert len(parts) == 3


class TestSubSplitSection:
    def test_short_section_not_split(self):
        parts = _sub_split_section("Short text", 3800)
        assert len(parts) == 1

    def test_splits_on_item_separator(self):
        items = ["A" * 2000, "B" * 2000]
        text = _ITEM_SEP.join(items)
        parts = _sub_split_section(text, 3800)
        assert len(parts) == 2


class TestComposeItemCard:
    def test_basic_card(self):
        item = FakeSynthesizedItem(
            title="Test Title",
            summary_ru="Summary text",
            why_it_matters="Important because",
        )
        card = _compose_item_card(item)
        assert "<b>Test Title</b>" in card
        assert "Summary text" in card
        assert "<i>Почему важно:</i>" in card
        assert "Important because" in card

    def test_card_without_why_it_matters(self):
        item = FakeSynthesizedItem(why_it_matters="")
        card = _compose_item_card(item)
        assert "Почему важно" not in card

    def test_card_has_sources(self):
        item = FakeSynthesizedItem()
        card = _compose_item_card(item)
        assert "example.com" in card

    def test_no_editor_take_in_card(self):
        item = FakeSynthesizedItem(editor_take="Some editorial opinion")
        card = _compose_item_card(item)
        assert "Редакция" not in card


class TestComposeDigestIssue:
    def test_basic_issue(self):
        items = {
            "world": make_items(5, "world"),
            "russia_moscow": make_items(5, "russia_moscow"),
            "ai_agents": make_items(3, "ai_agents"),
            "tech": make_items(2, "tech"),
            "games": make_items(5, "games"),
        }
        from datetime import date
        issue = compose_digest_issue(items, date(2026, 4, 15), "09:00")

        assert issue.item_count > 0
        assert len(issue.telegram_parts) >= 1
        assert "УТРЕННИЙ ДАЙДЖЕСТ" in issue.full_text
        assert "#главное" in issue.full_text
        assert "#world" in issue.full_text
        assert "#Москва" in issue.full_text
        assert "#ai" in issue.full_text
        assert "#games" in issue.full_text

    def test_5_sections(self):
        items = {
            "world": make_items(5, "world"),
            "russia_moscow": make_items(5, "russia_moscow"),
            "ai": make_items(5, "ai"),
            "games": make_items(5, "games"),
        }
        from datetime import date
        issue = compose_digest_issue(items, date(2026, 4, 15), "09:00")
        # Header/Главное + 4 category sections (ai_agents empty → ai still present)
        sections = issue.full_text.split(_SECTION_SEP)
        assert len(sections) >= 2  # at least header + some categories

    def test_hard_limit_5_items(self):
        items = {"world": make_items(10, "world")}
        from datetime import date
        issue = compose_digest_issue(items, date(2026, 4, 15), "09:00")
        # Count item cards in world section (separated by _ITEM_SEP)
        world_section = [s for s in issue.full_text.split(_SECTION_SEP) if "Мировые новости" in s]
        if world_section:
            card_count = world_section[0].count("<b>News ")
            assert card_count <= 5

    def test_empty_categories(self):
        from datetime import date
        issue = compose_digest_issue({}, date(2026, 4, 15), "09:00")
        assert issue.item_count == 0
        assert "УТРЕННИЙ ДАЙДЖЕСТ" in issue.full_text
