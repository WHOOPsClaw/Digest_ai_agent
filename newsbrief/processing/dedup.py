"""digest/dedup.py — deduplication for news digest pipeline.

Two stages:
  1. deduplicate_against_batch  — remove intra-batch duplicates before any DB touch
  2. deduplicate_against_db     — filter out articles already stored for this date

Dedup keys (any single match marks an article as duplicate):
  a. exact URL            — same page, regardless of title
  b. normalized title     — same headline from different sources
  c. url_hash             — SHA-256(normalize_title(title) + "|" + url.strip())
                            this is the value written to digest_items.url_hash

No LLM involved. Pure string/hash logic.

────────────────────────────────────────────────────────────────────────────
Rules
────────────────────────────────────────────────────────────────────────────
• normalize_title:   lowercase → strip non-word chars → collapse whitespace
                     "Apple's AI — новые модели!" → "apples ai новые модели"
• url_hash:          SHA-256 of  normalize_title(title) + "|" + url.strip()
                     The "|" separator prevents (title="a", url="|b") from
                     colliding with (title="a|", url="b").
• Batch dedup:       first occurrence wins; later duplicates are dropped.
• DB dedup:          queries digest_items for this date, returns only articles
                     whose url_hash is not yet stored.

────────────────────────────────────────────────────────────────────────────
Example before / after
────────────────────────────────────────────────────────────────────────────
Input batch (category=ai, date=2025-06-10):

  1. title="OpenAI releases GPT-5"   url="https://techcrunch.com/a"  source=search
  2. title="OpenAI releases GPT-5"   url="https://bbc.com/b"         source=rss:bbc
  3. title="OpenAI Releases GPT-5!"  url="https://techcrunch.com/a"  source=rss:tc
  4. title="Meta AI announcement"    url="https://meta.com/c"        source=search
  5. title="Meta AI Announcement"    url="https://meta.com/c"        source=rss:ign

After deduplicate_against_batch:
  → 1 kept  (first)
  → 2 dropped (same norm title "openai releases gpt 5")
  → 3 dropped (same url AND same norm title)
  → 4 kept
  → 5 dropped (same url "https://meta.com/c")

After deduplicate_against_db (assume article 4 already in DB from yesterday):
  → 1 kept
  → 4 dropped (url_hash already in digest_items for this date)
  Result: [article 1]
"""

from __future__ import annotations

import os
import re
import hashlib
import logging
from datetime import date as _date
# db_pool imported lazily
from typing import List, Set

# psycopg2 lazy

from newsbrief.core.models import RawArticle

logger = logging.getLogger("uvicorn.error")


# ---------------------------------------------------------------------------
# DB connection (mirrors storage.py — same env vars, intentionally duplicated)
# ---------------------------------------------------------------------------

# Connection pool — see db_pool.py


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------

_NON_WORD_RE = re.compile(r"[^\w\s]", re.UNICODE)
_SPACE_RE    = re.compile(r"\s+")


def normalize_title(title: str) -> str:
    """Normalize a title for dedup comparison.

    Steps: lowercase → strip non-word chars → collapse whitespace.
    Example: "Apple's AI — новые модели!" → "apples ai  новые модели"
    Returns empty string if input is empty/whitespace-only.
    """
    t = title.lower()
    t = _NON_WORD_RE.sub(" ", t)
    t = _SPACE_RE.sub(" ", t).strip()
    return t


def build_url_hash(title: str, url: str) -> str:
    """Return SHA-256 hex digest of normalize_title(title) + "|" + url.strip().

    This is the value stored in digest_items.url_hash.
    The "|" separator ensures no accidental collisions between title and url parts.
    """
    payload = normalize_title(title) + "|" + url.strip()
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Stage 1: batch dedup
# ---------------------------------------------------------------------------

def _simhash(text: str, bits: int = 64) -> int:
    """Compute a bits-wide SimHash over whitespace tokens of ``text``."""
    tokens = (text or "").lower().split()
    if not tokens:
        return 0
    v = [0] * bits
    mask = (1 << bits) - 1
    for tok in tokens:
        h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16) & mask
        for i in range(bits):
            if h & (1 << i):
                v[i] += 1
            else:
                v[i] -= 1
    sig = 0
    for i in range(bits):
        if v[i] > 0:
            sig |= (1 << i)
    return sig


def _hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def fast_dedup(articles, threshold: int = 4):
    """Dedup a batch of articles by SimHash Hamming distance.

    Used when the batch is large enough that exact-match dedup is insufficient
    (minor textual variants from aggregators). Complexity is O(N^2) but with
    cheap 64-bit int operations, so works up to a few thousand items.
    """
    seen_hashes: list = []
    result: list = []
    for a in articles:
        title = getattr(a, "title", "") or ""
        snippet = getattr(a, "snippet", "") or ""
        sig = _simhash(title + " " + snippet[:200])
        if any(_hamming(sig, h) < threshold for h in seen_hashes):
            continue
        seen_hashes.append(sig)
        result.append(a)
    return result


def deduplicate_against_batch(articles: List[RawArticle]) -> List[RawArticle]:
    """Remove intra-batch duplicates. First occurrence wins.

    An article is considered a duplicate if ANY of these match a prior article:
      - exact URL (stripped)
      - normalized title
      - url_hash

    Returns a new list (input is not mutated).
    """
    seen_urls:   Set[str] = set()
    seen_titles: Set[str] = set()
    seen_hashes: Set[str] = set()
    result: List[RawArticle] = []

    for a in articles:
        url  = a.url.strip()
        nt   = normalize_title(a.title)
        h    = build_url_hash(a.title, a.url)

        if url in seen_urls or nt in seen_titles or h in seen_hashes:
            logger.debug(
                "[dedup] batch drop title=%r url=%r",
                a.title[:60], url[:80],
            )
            continue

        seen_urls.add(url)
        if nt:                 # only track non-empty normalized titles
            seen_titles.add(nt)
        seen_hashes.add(h)
        result.append(a)

    dropped = len(articles) - len(result)
    if dropped:
        logger.info("[dedup] batch: %d→%d (dropped %d)", len(articles), len(result), dropped)

    # For large batches, apply SimHash fuzzy pass on top of exact-match result
    if len(result) > 50:
        before = len(result)
        result = fast_dedup(result)
        if len(result) < before:
            logger.info(
                "[dedup] simhash: %d→%d (dropped %d near-duplicates)",
                before, len(result), before - len(result),
            )
    return result


# ---------------------------------------------------------------------------
# Stage 2: DB dedup
# ---------------------------------------------------------------------------

def _get_existing_hashes(digest_date: _date, lookback_days: int = 7) -> Set[str]:
    """Return url_hash values from the last lookback_days days + today.

    Anti-repeat window: prevents the same article from appearing in the digest
    if it was already published in the last N days.
    """
    from datetime import timedelta
    cutoff = digest_date - timedelta(days=lookback_days)
    try:
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT url_hash FROM digest_items WHERE digest_date >= %s AND digest_date <= %s",
                (cutoff, digest_date),
            )
            rows = cur.fetchall()
            cur.close()
        if rows:
            logger.info("[dedup] anti-repeat: loaded %d hashes from last %d days", len(rows), lookback_days)
        return {r[0] for r in rows}
    except Exception as e:
        logger.error("[dedup] _get_existing_hashes failed date=%s: %s", digest_date, e)
        return set()


def deduplicate_against_db(
    articles: List[RawArticle],
    digest_date: _date,
) -> List[RawArticle]:
    """Filter out articles already in digest_items from the last 7 days.

    Comparison key: url_hash = SHA-256(normalize_title(title) + "|" + url).
    Lookback window prevents the same article from re-appearing across daily fetches.

    On DB error: logs and returns the full list unchanged (fail-open —
    better to process a duplicate than to silently drop new content).
    """
    if not articles:
        return []

    existing = _get_existing_hashes(digest_date)
    if not existing:
        return articles          # either empty table or DB error (fail-open)

    result   = [a for a in articles if build_url_hash(a.title, a.url) not in existing]
    dropped  = len(articles) - len(result)
    if dropped:
        logger.info(
            "[dedup] db: %d→%d (dropped %d already in db for %s)",
            len(articles), len(result), dropped, digest_date,
        )
    return result
