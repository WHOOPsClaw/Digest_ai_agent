"""digest/ranker.py — Personalized event ranking layer.

Inserted between group_similar_articles() and synthesize_category_digest()
in service.py when DIGEST_USE_RANKED=true (default: true).

Pipeline:
    events = group_similar_articles(articles)
    events = rank_events_for_user(events, category, top_n=max_events)  # <- new
    items  = synthesize_category_digest(events, max_events=max_events, ...)

Each DigestEvent gets 5 score fields set in-place:
    freshness_score          0-1
    source_confidence_score  0-1
    global_importance_score  0-1
    personal_relevance_score 0-1
    final_score              0-1  (weighted sum, weights differ per category)
"""

from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Dict, List

# ---------------------------------------------------------------------------
# User Relevance Profile
# ---------------------------------------------------------------------------

USER_RELEVANCE_PROFILE: Dict = {
    # Base weight per category (applied as floor for personal_relevance)
    "category_weights": {
        "ai_agents":     1.0,
        "ai":            0.95,
        "tech":          0.9,
        "russia_moscow": 0.8,
        "world":         0.75,
        "games":         0.65,
    },
    # Topic keywords per category — match against event title + snippets
    "topic_keywords": {
        "ai_agents": [
            "openclaw", "agent", "coding agent", "mcp", "tool call",
            "browser", "memory", "voice", "search", "local model",
            "ollama", "routing", "orchestration", "agent framework",
            "plugin", "claude", "openai", "anthropic", "langchain",
            "cursor", "copilot", "agentic", "workflow", "function call",
            "llm stack", "tool use", "skill", "autonomous",
        ],
        "ai": [
            "llm", "gpt", "claude", "gemini", "llama", "model",
            "inference", "fine-tun", "rag", "embedding", "vector",
            "benchmark", "reasoning", "multimodal", "context window",
            "open source model", "weights",
        ],
        "tech": [
            "apple", "mac", "macbook", "apple silicon", " m1", " m2", " m3", " m4",
            "developer", "ide", "vscode", "github", "automation",
            "docker", "open source", "rust", "golang",
        ],
        "games": [
            "release", "launch", "announced", "trailer", "studio",
            "sony", "microsoft", "nintendo", "valve", "steam",
            "indie", "rpg", "fps", "open world", "game development",
        ],
        "russia_moscow": [
            "москва", "метро", "транспорт", "перекрытие", "дтп",
            "протест", "суд", "закон", "мэрия", "правительство",
            "улица", "центр", "район", "происшествие", "штраф",
            "кремль", "арест", "митинг",
        ],
        "world": [
            "война", "конфликт", "war", "conflict", "economy", "trade",
            "sanctions", "election", "president", "nato", "un",
            "climate", "energy", "market", "crisis",
            "геополитика", "переговоры", "блокада",
        ],
    },
}

# Trusted source fragments (global fallback)
_TRUSTED_GLOBAL = frozenset({
    "reuters", "apnews", "bbc", "guardian", "nytimes", "washingtonpost",
    "ft.com", "economist", "techcrunch", "theverge", "wired", "arstechnica",
    "simonwillison", "latent.space", "kommersant", "vedomosti", "rbc", "meduza",
    "anthropic", "openai", "google", "microsoft", "github", "huggingface",
    "langchain",
})

# Category-specific trusted sources (subset/superset of global)
_TRUSTED_BY_CAT: Dict[str, frozenset] = {
    "ai_agents": frozenset({
        "anthropic", "openai", "google", "langchain", "huggingface",
        "simonwillison", "latent.space", "github", "cursor",
    }),
    "ai": frozenset({
        "anthropic", "openai", "deepmind", "mistral", "huggingface",
        "techcrunch", "theverge", "latent.space",
    }),
    "tech": frozenset({
        "techcrunch", "theverge", "arstechnica", "wired",
        "apple.com", "github", "microsoft",
    }),
    "world": frozenset({
        "reuters", "apnews", "bbc", "guardian", "ft.com",
        "economist", "nytimes", "washingtonpost",
    }),
    "russia_moscow": frozenset({
        "kommersant", "vedomosti", "rbc", "meduza",
        "tass", "fontanka", "mos.ru",
    }),
    "games": frozenset({
        "ign", "gamespot", "kotaku", "steam", "shazoo",
        "nintendo", "sony", "microsoft", "valve",
    }),
}

# Importance signals per category — strong-signal words in title/text
_IMPORTANCE_SIGNALS: Dict[str, frozenset] = {
    "world": frozenset({
        "война", "war", "attack", "election", "president", "nato",
        "блокада", "санкции", "sanctions", "crisis", "конфликт",
        "nuclear", "treaty", "ceasefire", "summit", "explosion",
        "major", "global", "international",
    }),
    "russia_moscow": frozenset({
        "арест", "суд", "протест", "закон", "мэрия", "кремль",
        "путин", "перекрытие", "происшествие", "взрыв", "пожар",
        "министр", "правительство", "запрет", "обыск", "задержан",
    }),
    "ai_agents": frozenset({
        "release", "released", "launch", "announced", "new model",
        "new agent", "новая модель", "выпустил", "запустил",
        "gpt", "claude", "gemini", "llama", "open source",
    }),
    "ai": frozenset({
        "release", "released", "launch", "model", "benchmark",
        "breakthrough", "outperforms", "new", "open source",
        "state of the art", "sota",
    }),
    "tech": frozenset({
        "apple", "google", "microsoft", "amazon", "ipo", "billion",
        "launch", "release", "new product", "open source",
    }),
    "games": frozenset({
        "release", "launch", "announced", "major", "ps5", "xbox",
        "nintendo", "new game", "sequel", "remake", "goty",
    }),
}

# Final-score weights per category:  A*global + B*personal + C*freshness + D*source
_SCORE_WEIGHTS: Dict[str, tuple] = {
    "world":         (0.40, 0.25, 0.20, 0.15),
    "russia_moscow": (0.30, 0.35, 0.20, 0.15),
    "ai_agents":     (0.22, 0.48, 0.15, 0.15),
    "ai":            (0.28, 0.42, 0.15, 0.15),
    "tech":          (0.30, 0.35, 0.20, 0.15),
    "games":         (0.25, 0.38, 0.27, 0.10),
}
_DEFAULT_WEIGHTS = (0.33, 0.33, 0.19, 0.15)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_source(raw: str) -> str:
    """Strip rss:/tg:/search: prefix from source field."""
    return re.sub(r"^(rss:|tg:|search:?)\s*", "", (raw or "").lower()).strip()


def _event_text(event) -> str:
    """Lowercase text of event title + article snippets (first 300 chars each)."""
    parts = [(event.canonical_title or "").lower()]
    for a in event.articles:
        snippet = (getattr(a, "snippet", "") or "").strip()
        if snippet:
            parts.append(snippet[:300].lower())
    return " ".join(parts)


def _token_set(event) -> frozenset:
    """Meaningful tokens (≥4 chars) from event text — used for diversity filter."""
    return frozenset(re.findall(r"[а-яёa-z]{4,}", _event_text(event)))


# ---------------------------------------------------------------------------
# Score functions
# ---------------------------------------------------------------------------

def _compute_freshness(event) -> float:
    """0–1: how fresh is the event. Unknown timestamp → 0.5 (neutral)."""
    ts = event.published_at
    if ts is None:
        return 0.5
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    age_h = (datetime.now(timezone.utc) - ts).total_seconds() / 3600
    # 1.0 at 0h → ~0.5 at 24h → ~0.05 at 48h
    return max(0.05, 1.0 - age_h / 48.0)


def _compute_source_confidence(event, category: str) -> float:
    """0–1: quality and trustworthiness of sources."""
    trusted_cat = _TRUSTED_BY_CAT.get(category, _TRUSTED_GLOBAL)
    n = len(event.articles)
    if n == 0:
        return 0.0

    score = 0.0
    for a in event.articles:
        src = _clean_source(getattr(a, "source", ""))
        if any(t in src for t in trusted_cat):
            score += 0.35
        elif any(t in src for t in _TRUSTED_GLOBAL):
            score += 0.20
        else:
            score += 0.05

    # Multi-source bonus
    score += 0.25 if n >= 4 else (0.10 if n >= 2 else 0.0)

    # Role-based bonus
    role = getattr(event, "role", "source")
    if role == "verified":
        score += 0.20
    elif role == "partially_verified":
        score += 0.10

    return min(1.0, score)


def _compute_global_importance(event, category: str) -> float:
    """0–1: objective importance heuristic, category-aware."""
    score = 0.0
    n     = len(event.articles)
    title = (event.canonical_title or "").lower()
    text  = _event_text(event)

    # Coverage breadth (more articles = broader coverage)
    score += min(0.40, n * 0.10)

    # Domain diversity
    domains = {_clean_source(getattr(a, "source", "")) for a in event.articles}
    score += min(0.15, len(domains) * 0.05)

    # Importance signal keywords
    signals = _IMPORTANCE_SIGNALS.get(category, frozenset())
    hits    = sum(1 for sig in signals if sig in title or sig in text)
    score  += min(0.35, hits * 0.12)

    # Snippet richness proxy
    avg_len = sum(len(getattr(a, "snippet", "") or "") for a in event.articles) / max(1, n)
    score  += min(0.10, avg_len / 1200)

    return min(1.0, score)


def _compute_personal_relevance(event, category: str) -> float:
    """0–1: relevance to this specific user's interests."""
    profile    = USER_RELEVANCE_PROFILE
    cat_weight = profile["category_weights"].get(category, 0.7)
    topic_kws  = profile["topic_keywords"].get(category, [])
    text       = _event_text(event)

    if not topic_kws:
        return cat_weight * 0.5

    hits     = sum(1 for kw in topic_kws if kw in text)
    # Log-dampen to avoid gaming with long keyword lists
    kw_score = min(1.0, hits / max(1.0, math.log2(len(topic_kws) + 2)))

    # Base = category weight, boosted by keyword matches
    return min(1.0, cat_weight * 0.35 + kw_score * 0.65)


# ---------------------------------------------------------------------------
# Composite score
# ---------------------------------------------------------------------------

def score_event(event, category: str) -> Dict[str, float]:
    """Compute all five scores for one DigestEvent.

    Returns dict with keys matching DigestEvent score field names.
    """
    fresh  = _compute_freshness(event)
    src_c  = _compute_source_confidence(event, category)
    g_imp  = _compute_global_importance(event, category)
    p_rel  = _compute_personal_relevance(event, category)

    A, B, C, D = _SCORE_WEIGHTS.get(category, _DEFAULT_WEIGHTS)
    final = A * g_imp + B * p_rel + C * fresh + D * src_c

    return {
        "freshness_score":          round(fresh, 4),
        "source_confidence_score":  round(src_c, 4),
        "global_importance_score":  round(g_imp, 4),
        "personal_relevance_score": round(p_rel, 4),
        "final_score":              round(final, 4),
    }


# ---------------------------------------------------------------------------
# Diversity filter
# ---------------------------------------------------------------------------

def _select_with_diversity(ranked: List, top_n: int, sim_threshold: float = 0.40) -> List:
    """Greedy diversity selection: prefer high-scored, non-similar events.

    Similarity = token Jaccard on event text.
    Events with overlap >= sim_threshold vs an already-selected event are skipped.
    Backfills from skipped pool if diversity was too aggressive.
    """
    selected: List = []
    skipped:  List = []

    for ev in ranked:
        if len(selected) >= top_n:
            break
        ev_tok = _token_set(ev)
        too_similar = False
        for sel in selected:
            sel_tok = _token_set(sel)
            union   = sel_tok | ev_tok
            if not union:
                continue
            if len(sel_tok & ev_tok) / len(union) >= sim_threshold:
                too_similar = True
                break
        if too_similar:
            skipped.append(ev)
        else:
            selected.append(ev)

    # Backfill if diversity filter removed too many
    if len(selected) < top_n:
        for ev in skipped:
            if len(selected) >= top_n:
                break
            selected.append(ev)

    return selected


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def rank_events_for_user(
    events:        List,
    category:      str,
    top_n:         int  = 0,
    use_diversity: bool = True,
) -> List:
    """Score, rank, and optionally select top events for the user.

    Mutates each DigestEvent in-place (sets score attributes).
    Returns events sorted by final_score DESC.

    Args:
        events:        List[DigestEvent] from group_similar_articles()
        category:      category slug ("world", "ai_agents", etc.)
        top_n:         if > 0, return at most top_n events (with diversity filter)
        use_diversity: apply diversity dedup when selecting top_n (default True)

    Returns:
        Sorted (and optionally trimmed) List[DigestEvent].
        Returns empty list unchanged if input is empty.
    """
    if not events:
        return events

    for ev in events:
        scores = score_event(ev, category)
        for attr, val in scores.items():
            setattr(ev, attr, val)

    ranked = sorted(events, key=lambda e: getattr(e, "final_score", 0.0), reverse=True)

    if top_n > 0:
        if use_diversity:
            return _select_with_diversity(ranked, top_n)
        return ranked[:top_n]

    return ranked
