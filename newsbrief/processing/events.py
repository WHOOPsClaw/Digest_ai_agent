"""digest/events.py — group RawArticles into DigestEvents.

Primary method: keyword overlap heuristic (no LLM required).
Optional: LLM-assisted canonical title refinement (DIGEST_LLM_TITLES=true).

Group criteria (any two articles merged into same event if):
  1. Jaccard(keywords_a, keywords_b) >= DIGEST_JACCARD_THRESHOLD  (default 0.20)
  OR
  2. |keywords_a ∩ keywords_b| >= DIGEST_MIN_SHARED_KW             (default 2)
  AND
  3. published_at within DIGEST_TIME_DELTA_H hours of each other   (default 24h)
     — articles with unknown publish time are NOT penalized (treated as "close enough")

Union-Find ensures transitive closure: if A~B and B~C, all three form one event.

────────────────────────────────────────────────────────────────────────────
Example grouping
────────────────────────────────────────────────────────────────────────────
Input (category=ai):
  1. "OpenAI releases GPT-5 for enterprise"      source=search
  2. "OpenAI GPT-5 launch date confirmed"         source=rss:techcrunch_ai
  3. "Google DeepMind announces Gemini 2.0"       source=rss:ai_news
  4. "GPT-5 enterprise pricing details"           source=rss:ai_news
  5. "Gemini 2.0 vs GPT-4 benchmark results"      source=search

Keywords extracted (after stopwords removal):
  1. {openai, releases, gpt, enterprise}
  2. {openai, gpt, launch, date, confirmed}
  3. {google, deepmind, announces, gemini}
  4. {gpt, enterprise, pricing, details}
  5. {gemini, benchmark, results, gpt}

Pairwise similarities:
  1↔2: shared={openai,gpt}=2 → MERGE
  1↔4: shared={gpt,enterprise}=2 → MERGE  (transitive: 1+2+4 in same group)
  3↔5: shared={gemini}=1, jaccard=1/7≈0.14 → NO MERGE (below both thresholds)
  2↔4: shared={gpt}=1 → NO MERGE alone, but already in group via 1
  5↔3: jaccard=1/7 → NO MERGE

Result events:
  Event A (3 articles): canonical="OpenAI GPT-5 launch date confirmed" [rss:techcrunch_ai]
    sources: techcrunch.com, openai-blog.com, ai_news_site.com
  Event B (1 article): canonical="Google DeepMind announces Gemini 2.0"
  Event C (1 article): canonical="Gemini 2.0 vs GPT-4 benchmark results"
"""

from __future__ import annotations

import os
import re
import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set

from newsbrief.core.models import RawArticle
from .dedup import normalize_title

logger = logging.getLogger("uvicorn.error")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

JACCARD_THRESHOLD   = float(os.getenv("DIGEST_JACCARD_THRESHOLD", "0.20"))
MIN_SHARED_KEYWORDS = int(os.getenv("DIGEST_MIN_SHARED_KW",       "2"))
MAX_TIME_DELTA_H    = int(os.getenv("DIGEST_TIME_DELTA_H",         "24"))
DIGEST_LLM_TITLES   = os.getenv("DIGEST_LLM_TITLES", "false").lower() == "true"
AI_WORKER_URL       = os.getenv("AI_WORKER_URL", "http://localhost:8001")
AI_WORKER_TIMEOUT   = float(os.getenv("AI_WORKER_TIMEOUT", "120"))


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class DigestEvent:
    category:        str
    canonical_title: str
    articles:        List[RawArticle]
    sources:         List[dict]          # [{url, title, source, published_at}]
    published_at:    Optional[datetime]  # earliest known publish time across articles
    role:            str = "source"  # "verified" | "partially_verified" | "signal_only"
    # Ranking scores — set by ranker.rank_events_for_user(); default 0.0
    freshness_score:          float = 0.0
    source_confidence_score:  float = 0.0
    global_importance_score:  float = 0.0
    personal_relevance_score: float = 0.0
    final_score:              float = 0.0


# ---------------------------------------------------------------------------
# Keyword extraction
# ---------------------------------------------------------------------------

# Stopwords: short function words in English and Russian
_STOPWORDS: Set[str] = {
    # English
    "the", "and", "for", "are", "was", "were", "has", "have", "had",
    "will", "would", "could", "should", "may", "might", "not", "its",
    "this", "that", "from", "with", "says", "said", "after", "than",
    "more", "also", "over", "new", "first", "last", "also", "into",
    "been", "being", "about", "where", "when", "who", "what", "how",
    # Russian
    "это", "так", "уже", "всё", "один", "два", "три", "без",
    "если", "том", "тем", "над", "под", "через", "между", "после",
    "при", "всех", "всем",
}

# Short words (≤ 2 chars) are always stopwords — no need to list them
_TOKEN_RE = re.compile(r"[a-zа-яё]{3,}", re.UNICODE)


def _keywords(title: str) -> Set[str]:
    """Extract meaningful keyword set from a title."""
    tokens = _TOKEN_RE.findall(normalize_title(title))
    return {t for t in tokens if t not in _STOPWORDS}


def _jaccard(a: Set[str], b: Set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Normalize datetime to UTC-aware. Returns None for None."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _time_close(a: Optional[datetime], b: Optional[datetime]) -> bool:
    """True if articles are temporally compatible.

    Returns True when either time is unknown (fail-open: don't discard
    valid groupings just because RSS feed omitted a timestamp).
    Normalizes both to UTC to avoid naive/aware comparison TypeError.
    """
    a, b = _ensure_utc(a), _ensure_utc(b)
    if a is None or b is None:
        return True
    return abs((a - b).total_seconds()) <= MAX_TIME_DELTA_H * 3600


# ---------------------------------------------------------------------------
# Union-Find with path compression
# ---------------------------------------------------------------------------

class _UnionFind:
    def __init__(self, n: int):
        self._p = list(range(n))

    def find(self, x: int) -> int:
        while self._p[x] != x:
            self._p[x] = self._p[self._p[x]]  # path halving
            x = self._p[x]
        return x

    def union(self, x: int, y: int) -> None:
        self._p[self.find(x)] = self.find(y)

    def groups(self) -> Dict[int, List[int]]:
        d: Dict[int, List[int]] = defaultdict(list)
        for i in range(len(self._p)):
            d[self.find(i)].append(i)
        return dict(d)


# ---------------------------------------------------------------------------
# Main grouping
# ---------------------------------------------------------------------------


def _compute_event_role(articles) -> str:
    """Derive event-level confidence from constituent article roles.

    verified           = has at least one official source article
    partially_verified = has analysis/signal but no official source
    signal_only        = only signal (Telegram / search) sources
    """
    roles = {getattr(a, "role", "source") for a in articles}
    if "source" in roles:
        return "verified"
    if "analysis" in roles:
        return "partially_verified"
    return "signal_only"


def group_similar_articles(articles: List[RawArticle]) -> List[DigestEvent]:
    """Group articles about the same real-world event by keyword overlap.

    Steps:
      1. Extract keyword set per article.
      2. O(n²) pairwise comparison within the category batch.
         n is typically small (< 50 articles per category) so O(n²) is fine.
      3. Union-Find for transitive closure.
      4. Assemble DigestEvent per group.

    Returns events sorted: multi-article events first, then by publish time descending.
    Solo articles (no matches) each become their own DigestEvent.
    """
    if not articles:
        return []

    n   = len(articles)
    kws = [_keywords(a.title) for a in articles]
    uf  = _UnionFind(n)

    # Inverted index: token → list of article indices containing that token.
    # Candidate pairs only need to be compared if they share at least one token.
    token_to_ids: Dict[str, List[int]] = defaultdict(list)
    for i, ks in enumerate(kws):
        for tok in ks:
            token_to_ids[tok].append(i)

    checked: Set[tuple] = set()
    for i in range(n):
        if not kws[i]:
            continue
        candidates: Set[int] = set()
        for tok in kws[i]:
            candidates.update(token_to_ids.get(tok, ()))
        for j in candidates:
            if j <= i:
                continue
            key = (i, j)
            if key in checked:
                continue
            checked.add(key)
            if not kws[j]:
                continue
            shared  = len(kws[i] & kws[j])
            jaccard = _jaccard(kws[i], kws[j])
            if (jaccard >= JACCARD_THRESHOLD or shared >= MIN_SHARED_KEYWORDS):
                if _time_close(articles[i].published_at, articles[j].published_at):
                    uf.union(i, j)

    events: List[DigestEvent] = []
    for _, indices in uf.groups().items():
        group = [articles[i] for i in sorted(indices)]
        events.append(DigestEvent(
            category=        group[0].category,
            canonical_title= choose_canonical_title(group),
            articles=        group,
            sources=         collect_sources(group),
            published_at=    _earliest_time(group),
            role=            _compute_event_role(group),
        ))

    events.sort(key=lambda e: (-len(e.articles), _time_sort_key(e.published_at)))

    logger.info(
        "[events] %d articles → %d events (jaccard>=%.2f shared>=%d)",
        n, len(events), JACCARD_THRESHOLD, MIN_SHARED_KEYWORDS,
    )
    return events


def _earliest_time(articles: List[RawArticle]) -> Optional[datetime]:
    times = [a.published_at for a in articles if a.published_at is not None]
    return min(times) if times else None


def _time_sort_key(dt: Optional[datetime]) -> float:
    """Newer → smaller sort key. Events with no time sort to the end."""
    if dt is None:
        return float("inf")
    return -dt.timestamp()


# ---------------------------------------------------------------------------
# Canonical title selection
# ---------------------------------------------------------------------------

# Trusted RSS sources, checked in priority order
_PREFERRED_SOURCES = [
    # World
    "rss:reuters",
    "rss:bbc_world",
    "rss:guardian",
    "rss:aljazeera",
    # Russia/Moscow
    "rss:tass",
    "rss:rbc_news",
    "rss:kommersant",
    "rss:lenta_news",
    "rss:lenta_russia",
    "rss:mos_gov",
    # AI
    "rss:techcrunch_ai",
    "rss:huggingface",
    "rss:ai_news",
    # Games
    "rss:ign",
    "rss:kotaku",
    "rss:gamespot",
    "rss:pcgamer",
    # Tech
    "rss:techcrunch",
    "rss:theverge",
    "rss:arstechnica",
    # Telegram (lower priority than RSS, higher than search)
    "tg:pekagame",
    "tg:DyadyaLyoshaChannel",
    "tg:varlamov_news",
    # AI agents (official sources first, then analysis)
    "rss:anthropic",
    "rss:google_ai",
    "rss:github_blog",
    "rss:langchain",
    "rss:simon_willison",
    "rss:latent_space",
    "rss:techcrunch_ai",
    "rss:theverge_ai",
    "rss:infoq_ai",
    "tg:neuraldvig",
]


def choose_canonical_title(articles: List[RawArticle]) -> str:
    """Select the best representative title for a group of articles.

    Priority:
      1. Title from a preferred trusted source (≤ 120 chars, ≥ 3 words).
      2. Shortest complete title among all articles (≥ 3 words, ≤ 120 chars).
      3. First article's title as unconditional fallback.

    If DIGEST_LLM_TITLES=true, the chosen title is optionally refined by LLM.
    LLM failure always falls back silently to the heuristic result.
    """
    if not articles:
        return ""

    # 1. Preferred source
    for preferred in _PREFERRED_SOURCES:
        for a in articles:
            t = (a.title or "").strip()
            if a.source == preferred and 3 <= len(t.split()) and len(t) <= 120:
                return _maybe_llm_refine(t, articles)

    # 2. Shortest complete title
    candidates = [
        (a.title or "").strip() for a in articles
        if len((a.title or "").split()) >= 3 and len((a.title or "").strip()) <= 120
    ]
    if candidates:
        best = min(candidates, key=len)
        return _maybe_llm_refine(best, articles)

    # 3. Fallback
    return (articles[0].title or "").strip()


def _maybe_llm_refine(title: str, articles: List[RawArticle]) -> str:
    """Optional LLM title refinement. Returns original title on any failure."""
    if not DIGEST_LLM_TITLES:
        return title
    try:
        import httpx
        related = "; ".join(
            a.title.strip() for a in articles[:4]
            if a.title and a.title.strip() != title
        )
        prompt = (
            "Write a single clean news headline in Russian, max 80 characters. "
            "Return only the headline text, no quotes, no explanation.\n\n"
            f"Primary title: {title}\n"
            + (f"Related titles: {related}" if related else "")
        )
        with httpx.Client(timeout=30) as client:
            resp = client.post(
                f"{AI_WORKER_URL}/llm/generate",
                json={"prompt": prompt, "model": "main_local"},
            )
            resp.raise_for_status()
            result = resp.json().get("response", "").strip()
            # Sanity-check: single line, not too long, not empty
            if result and "\n" not in result and len(result) <= 120:
                logger.debug("[events] llm refined title: %r → %r", title[:60], result[:60])
                return result
    except Exception as e:
        logger.warning("[events] llm title refinement failed: %s", e)
    return title


# ---------------------------------------------------------------------------
# Source collection
# ---------------------------------------------------------------------------

def collect_sources(articles: List[RawArticle]) -> List[dict]:
    """Build a deduplicated source list from a group of articles.

    Returns list of {url, title, source, published_at}, deduplicated by URL.
    RSS sources sorted before search results (more reliable).
    """
    seen_urls: Set[str] = set()
    rss: List[dict]    = []
    search: List[dict] = []

    for a in articles:
        url = (a.url or "").strip()
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        entry = {
            "url":          url,
            "title":        (a.title or "").strip(),
            "source":       a.source,
            "published_at": a.published_at.isoformat() if a.published_at else None,
        }
        if a.source.startswith("rss:"):
            rss.append(entry)
        else:
            search.append(entry)

    return rss + search
