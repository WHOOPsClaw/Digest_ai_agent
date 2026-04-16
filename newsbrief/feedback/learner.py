"""feedback/learner.py — turn feedback into ranker boosts and blacklist hints.

High-level rules (see spec):
    * Sources with avg score > +0.3 → boost 1.5
    * Sources with avg score < −0.3 → boost 0.5
    * Below min_feedback total signals → neutral 1.0
    * Sources with 3+ 🔕 mutes in 30d → auto-blacklist candidate
"""
from __future__ import annotations

import logging
from typing import Any

from newsbrief.feedback.collector import get_feedback_stats

logger = logging.getLogger("newsbrief")

BOOST_HIGH = 1.5
BOOST_LOW  = 0.5
BOOST_NEUTRAL = 1.0


def compute_source_boosts(
    storage: Any,
    config: Any,  # noqa: ARG001 — reserved for future per-topic logic
    min_feedback: int = 10,
) -> dict[str, float]:
    """Return {source_id: boost_factor in [0.5, 2.0]} for the ranker.

    Sources with enough signal get boosted or demoted; otherwise neutral 1.0.
    """
    stats   = get_feedback_stats(storage, days=30)
    ratings = stats["source_ratings"]
    boosts: dict[str, float] = {}
    for src, bucket in ratings.items():
        total = bucket.get("total", 0)
        score = bucket.get("score", 0.0)
        if total < min_feedback:
            boosts[src] = BOOST_NEUTRAL
            continue
        if score > 0.3:
            boosts[src] = BOOST_HIGH
        elif score < -0.3:
            boosts[src] = BOOST_LOW
        else:
            boosts[src] = BOOST_NEUTRAL
    return boosts


def auto_blacklist_candidates(storage: Any, threshold: int = 3) -> list[str]:
    """Sources with `threshold`+ 🔕 mutes in last 30 days → candidates."""
    stats   = get_feedback_stats(storage, days=30)
    ratings = stats["source_ratings"]
    return [
        src for src, bucket in ratings.items()
        if bucket.get("blocked", 0) >= threshold
    ]


def _extract_blacklist_keywords(storage: Any, days: int, llm_router: Any = None) -> list[str]:
    """Look at feedback rows with down/block rating, extract recurring keywords.

    Uses llm_router if provided; otherwise falls back to simple token frequency
    on article_url strings (which include idx:N refs — fallback is cheap).
    """
    if storage is None:
        return []
    try:
        if getattr(storage, "is_postgres", False):
            sql = (
                "SELECT article_url, source FROM feedback "
                "WHERE rating IN ('down', 'mute', 'blocked') "
                "AND created_at >= NOW() - INTERVAL '%d days'" % int(days)
            )
        else:
            sql = (
                "SELECT article_url, source FROM feedback "
                "WHERE rating IN ('down', 'mute', 'blocked') "
                "AND created_at >= datetime('now', '-%d days')" % int(days)
            )
        rows = storage.fetchall(sql)
    except Exception as e:
        logger.warning("[learner] keyword extract failed: %s", e)
        return []

    if not rows:
        return []

    corpus = " ".join(
        f"{r.get('article_url') or ''} {r.get('source') or ''}" for r in rows
    )

    if llm_router is not None:
        try:
            prompt = (
                "Определи 3-5 ключевых тем/слов, которые часто встречаются "
                "в этих негативно оцененных новостях. Верни списком через запятую, "
                "только слова, без пояснений:\n\n" + corpus[:2000]
            )
            resp = llm_router.generate(prompt, task="filter")
            text = getattr(resp, "text", "") or str(resp)
            words = [w.strip().lower() for w in text.split(",") if w.strip()]
            return [w for w in words if 2 < len(w) < 40][:5]
        except Exception as e:
            logger.warning("[learner] llm keyword extract failed: %s", e)

    # Fallback: simple frequency
    import re
    from collections import Counter
    tokens = re.findall(r"[а-яёА-ЯЁa-zA-Z]{4,}", corpus.lower())
    stop = {"http", "https", "www", "com", "html", "idx", "rss", "feed", "news"}
    counts = Counter(t for t in tokens if t not in stop)
    return [w for w, c in counts.most_common(5) if c >= 2]


def suggest_adjustments(storage: Any, config: Any, days: int = 30, llm_router: Any = None) -> dict:
    """Analyze feedback and return actionable suggestions for config updates."""
    from newsbrief.feedback.collector import (
        get_source_ratings, get_blocked_sources,
    )
    ratings = get_source_ratings(storage, days=days)

    source_boosts: dict[str, float] = {}
    reasoning_lines: list[str] = []
    for src, bucket in ratings.items():
        if bucket["total"] >= 5 and bucket["score"] > 0.5:
            boost = min(0.5, 0.2 + 0.1 * (bucket["score"] - 0.5) * 2)
            source_boosts[src] = round(boost, 3)
            reasoning_lines.append(
                f"{src}: {bucket['up']} 👍 / {bucket['down']} 👎, "
                f"score={bucket['score']:.2f} → boost +{boost:.2f}"
            )

    remove_sources = get_blocked_sources(storage, days=days, threshold=3)
    for src in remove_sources:
        reasoning_lines.append(
            f"{src}: {ratings.get(src, {}).get('block', 0)} 🔕 — candidate for removal"
        )

    add_to_blacklist = _extract_blacklist_keywords(storage, days, llm_router=llm_router)
    if add_to_blacklist:
        reasoning_lines.append("blacklist keywords: " + ", ".join(add_to_blacklist))

    return {
        "source_boosts":    source_boosts,
        "add_to_blacklist": add_to_blacklist,
        "remove_sources":   remove_sources,
        "reasoning":        " | ".join(reasoning_lines) if reasoning_lines
                            else "No significant patterns found.",
    }


def apply_learning_suggestions(config: Any, suggestions: dict) -> Any:
    """Apply suggestion dict to a NewsbriefConfig. Returns the modified config.

    - boosts sources (records in config._source_boosts for ranker)
    - extends topic blacklists with suggested keywords
    - removes blocked sources from topic.sources dicts
    """
    boosts = suggestions.get("source_boosts", {}) or {}
    blacklist_adds = suggestions.get("add_to_blacklist", []) or []
    to_remove = set(suggestions.get("remove_sources", []) or [])

    # Stash boosts for the ranker to read (non-persistent attribute)
    existing = getattr(config, "_source_boosts", {}) or {}
    existing.update(boosts)
    try:
        setattr(config, "_source_boosts", existing)
    except Exception:
        pass

    for topic in getattr(config, "topics", []) or []:
        if blacklist_adds:
            merged = list(dict.fromkeys(list(topic.blacklist or []) + blacklist_adds))
            topic.blacklist = merged
        if to_remove and isinstance(getattr(topic, "sources", None), dict):
            topic.sources = {
                k: v for k, v in topic.sources.items() if k not in to_remove
            }

    return config


def apply_learning(storage: Any, config: Any) -> dict:
    """Compute the full learning update. Returns a suggestion report.

    Does NOT mutate config unless the caller explicitly wires it. We keep this
    side-effect-free so the CLI can preview before saving.
    """
    min_feedback = getattr(
        getattr(config, "learning", None), "min_feedback", 10
    )
    threshold = getattr(
        getattr(config, "learning", None), "auto_blacklist_threshold", 3
    )

    boosts = compute_source_boosts(storage, config, min_feedback=min_feedback)
    blacklisted = auto_blacklist_candidates(storage, threshold=threshold)

    boosted = sorted([s for s, b in boosts.items() if b > 1.0])
    demoted = sorted([s for s, b in boosts.items() if b < 1.0])

    return {
        "boosts":           boosts,
        "boosted":          boosted,
        "demoted":          demoted,
        "auto_blacklisted": blacklisted,
    }
