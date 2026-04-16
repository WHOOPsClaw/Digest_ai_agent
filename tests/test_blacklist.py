"""Tests for digest/service.py — blacklist matching."""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from newsbrief.processing.filter import _event_matches_blacklist, _word_matches
from conftest import FakeEvent, FakeRawArticle


class TestWordMatches:
    def test_exact_match(self):
        assert _word_matches("trump", "donald trump said something") is True

    def test_no_partial_match(self):
        """'trump' should NOT match 'trumpet'."""
        assert _word_matches("trump", "playing the trumpet loudly") is False

    def test_wildcard_match(self):
        """'trump*' should match 'trumpism'."""
        assert _word_matches("trump*", "rise of trumpism in politics") is True

    def test_wildcard_matches_exact(self):
        assert _word_matches("trump*", "trump announces policy") is True

    def test_short_word_ignored(self):
        assert _word_matches("a", "a b c") is False  # single char ignored

    def test_case_insensitive(self):
        # haystack is always lowered before calling
        assert _word_matches("путин", "путин подписал указ") is True

    def test_no_match(self):
        assert _word_matches("bitcoin", "ethereum prices surge") is False


class TestEventMatchesBlacklist:
    def test_empty_blacklist(self):
        event = FakeEvent(canonical_title="Any news")
        assert _event_matches_blacklist(event, []) is False

    def test_match_in_title(self):
        event = FakeEvent(canonical_title="Trump announces new policy")
        assert _event_matches_blacklist(event, ["trump"]) is True

    def test_no_match(self):
        event = FakeEvent(canonical_title="Weather forecast for Moscow")
        assert _event_matches_blacklist(event, ["trump"]) is False

    def test_match_in_article_snippet(self):
        article = FakeRawArticle(title="News", snippet="Trump policy update")
        event = FakeEvent(canonical_title="US Politics")
        event.articles = [article]
        assert _event_matches_blacklist(event, ["trump"]) is True

    def test_no_partial_match_trumpet(self):
        event = FakeEvent(canonical_title="Trumpet player wins award")
        assert _event_matches_blacklist(event, ["trump"]) is False

    def test_multi_word_blacklist(self):
        """Multi-word: all words must match."""
        event = FakeEvent(canonical_title="AI agents deploy to production")
        assert _event_matches_blacklist(event, ["ai agents"]) is True

    def test_multi_word_partial_no_match(self):
        event = FakeEvent(canonical_title="AI models improve accuracy")
        assert _event_matches_blacklist(event, ["ai agents"]) is False

    def test_wildcard_in_blacklist(self):
        event = FakeEvent(canonical_title="Cryptocurrency crashes again")
        assert _event_matches_blacklist(event, ["crypto*"]) is True
