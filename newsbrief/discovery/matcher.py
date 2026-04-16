"""Match free-text user interests to curated topics via LLM + keyword scoring."""
from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


def _build_prompt(interests_text: str, topics: dict[str, Any]) -> str:
    lines = [
        "You are a source-discovery assistant.",
        "The user described their news interests. Pick 2-5 most relevant topics from the catalog.",
        "",
        f"User interests:\n{interests_text.strip()}",
        "",
        "Available topics:",
    ]
    for tid, t in topics.items():
        kws = ", ".join(t.get("keywords", [])[:8])
        lines.append(f"- {tid} ({t.get('display_name', tid)}): keywords={kws}")
    lines.append("")
    lines.append(
        'Respond with ONLY JSON (no prose), shape: '
        '{"topics":[{"topic_id":"ai_ml","reasoning":"..."}, ...]}'
    )
    return "\n".join(lines)


def _extract_json(text: str) -> dict[str, Any]:
    """Extract first JSON object from free-form LLM text."""
    if not text:
        return {}
    # Strip code fences.
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        try:
            return json.loads(fence.group(1))
        except Exception:
            pass
    # First { ... last }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except Exception:
            pass
    try:
        return json.loads(text)
    except Exception:
        return {}


def _score_source(src: dict[str, Any], interests_lower: str) -> int:
    score = 0
    name = str(src.get("name") or "").lower()
    desc = str(src.get("description") or "").lower()
    tags = [str(t).lower() for t in (src.get("tags") or [])]
    for token in re.findall(r"[a-zа-я0-9]{3,}", interests_lower):
        if token in name:
            score += 3
        if token in desc:
            score += 2
        for tag in tags:
            if token == tag or token in tag:
                score += 2
    if src.get("recommended"):
        score += 5
    quality = str(src.get("quality") or "").lower()
    if quality == "high":
        score += 2
    elif quality == "medium":
        score += 1
    return score


def match_interests(
    interests_text: str,
    llm_router: Any,
    known_sources: dict[str, Any],
) -> list[dict[str, Any]]:
    """Match user interests to topics; return ranked list of topic suggestions."""
    topics: dict[str, Any] = (known_sources or {}).get("topics", {}) or {}
    if not topics:
        return []

    prompt = _build_prompt(interests_text, topics)

    matched_ids: list[tuple[str, str]] = []  # (topic_id, reasoning)
    try:
        resp = llm_router.generate(prompt, task="discovery", max_tokens=800)
        text = getattr(resp, "text", "") or ""
        data = _extract_json(text)
        for item in (data.get("topics") or []):
            tid = str(item.get("topic_id") or "").strip()
            if tid in topics:
                matched_ids.append((tid, str(item.get("reasoning") or "")))
    except Exception as e:
        logger.warning("LLM match failed, falling back to keyword scoring: %s", e)

    # Fallback / augmentation: keyword-match topics directly if LLM returned nothing.
    if not matched_ids:
        interests_lower = (interests_text or "").lower()
        scored: list[tuple[int, str]] = []
        for tid, t in topics.items():
            score = 0
            for kw in t.get("keywords", []):
                if kw.lower() in interests_lower:
                    score += 1
            if score > 0:
                scored.append((score, tid))
        scored.sort(reverse=True)
        matched_ids = [(tid, f"matched keywords in user text") for _, tid in scored[:5]]

    # Deduplicate preserving order.
    seen: set[str] = set()
    ordered: list[tuple[str, str]] = []
    for tid, reason in matched_ids:
        if tid not in seen:
            seen.add(tid)
            ordered.append((tid, reason))

    interests_lower = (interests_text or "").lower()
    results: list[dict[str, Any]] = []
    for tid, reasoning in ordered:
        topic = topics[tid]
        ranked_sources: list[dict[str, Any]] = []
        for src in topic.get("sources", []) or []:
            score = _score_source(src, interests_lower)
            ranked_sources.append(
                {
                    "source_ref": src,
                    "recommended": bool(src.get("recommended")),
                    "score": score,
                    "reason": (
                        "pre-curated recommendation"
                        if src.get("recommended")
                        else "keyword match"
                    ),
                }
            )
        ranked_sources.sort(
            key=lambda s: (s["recommended"], s["score"]), reverse=True
        )
        results.append(
            {
                "topic_id": tid,
                "display_name": topic.get("display_name", tid),
                "emoji": topic.get("emoji", "📰"),
                "reasoning": reasoning,
                "sources": ranked_sources,
            }
        )

    return results
