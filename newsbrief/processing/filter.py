"""processing/filter.py — blacklist matching for events."""
from __future__ import annotations

import re


def _word_matches(word: str, haystack: str) -> bool:
    """Match a single blacklist word against haystack.

    - "trump*" (trailing *) → prefix match (matches trump, trumpism)
    - "trump"  (no *)      → whole-word match (won't match trumpet)
    """
    if len(word) < 2:
        return False
    if word.endswith("*"):
        prefix = re.escape(word[:-1])
        return bool(re.search(r'\b' + prefix, haystack))
    return bool(re.search(r'\b' + re.escape(word) + r'\b', haystack))


def event_matches_blacklist(event, blacklist: list) -> bool:
    """True if event title/snippets match any blacklisted topic.

    Multi-word topic: all words must match individually.
    """
    if not blacklist:
        return False
    haystack = event.canonical_title.lower()
    for art in event.articles:
        haystack += " " + (art.title or "").lower() + " " + (art.snippet or "").lower()
    for topic in blacklist:
        words = topic.split()
        if words and all(_word_matches(w, haystack) for w in words):
            return True
    return False


# Legacy aliases for existing tests
_word_matches = _word_matches
_event_matches_blacklist = event_matches_blacklist
