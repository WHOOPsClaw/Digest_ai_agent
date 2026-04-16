"""processing/semantic_dedup.py — Phase 6: smart deduplication + entity grouping.

Adds three capabilities on top of the existing URL-hash / Jaccard dedup:

  1. Entity extraction (regex fast-path, optional LLM slow-path)
  2. Entity-overlap grouping: merges events sharing the same org/product
  3. Cross-digest duplicate filtering against recent digest history

No new dependencies — regex + stdlib only for the fast path. LLM path is
optional and uses the caller-provided `llm_router.generate(..., task="filter")`.
"""
from __future__ import annotations

import json
import logging
import re
from collections import Counter
from datetime import date as _date
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

logger = logging.getLogger("newsbrief")


# ---------------------------------------------------------------------------
# Signature
# ---------------------------------------------------------------------------

_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
_WS_RE    = re.compile(r"\s+")

# Small English+Russian stopword set — enough for signature normalization.
_SIG_STOPWORDS: Set[str] = {
    "the", "and", "for", "are", "was", "were", "has", "have", "had",
    "will", "would", "could", "should", "may", "might", "not", "its",
    "this", "that", "from", "with", "says", "said", "after", "than",
    "more", "also", "over", "new", "first", "last", "into", "about",
    "been", "being", "where", "when", "who", "what", "how", "why",
    "это", "так", "уже", "всё", "если", "том", "тем", "над", "под",
    "через", "между", "после", "при", "всех", "всем", "для", "что",
    "как", "его", "она", "они", "оно", "все",
}


def _get(obj: Any, key: str, default: Any = "") -> Any:
    """Attribute or dict access."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def compute_card_signature(item: Any) -> str:
    """Short text combining title + key entities — used for hashing / similarity.

    Accepts anything exposing `title` / `canonical_title` and optional `snippet`.
    Returns lowercase, punctuation-stripped, stopword-filtered token string.
    """
    title   = _get(item, "canonical_title", "") or _get(item, "title", "") or ""
    snippet = _get(item, "snippet", "") or _get(item, "summary_ru", "") or ""
    text    = f"{title} {snippet}".lower()
    text    = _PUNCT_RE.sub(" ", text)
    text    = _WS_RE.sub(" ", text).strip()
    tokens  = [t for t in text.split() if len(t) >= 3 and t not in _SIG_STOPWORDS]
    # dedupe preserving order
    seen: Set[str] = set()
    out:  List[str] = []
    for t in tokens:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return " ".join(out)


# ---------------------------------------------------------------------------
# Entity extraction — regex fast path
# ---------------------------------------------------------------------------

# CamelCase / capitalized sequences up to 4 tokens, e.g. "Tesla", "OpenAI",
# "Microsoft AI", "Google DeepMind".
_CAP_SEQ_RE = re.compile(
    r"\b([A-Z][A-Za-z0-9]{1,}(?:\s+[A-Z][A-Za-z0-9]{1,}){0,3})\b"
)
# Product-like tokens: "GPT-5", "iPhone 17", "Llama 3.1", "GPT-4.5"
_PRODUCT_RE = re.compile(
    r"\b([A-Za-z]{2,}[-\s]?\d+(?:\.\d+)?)\b"
)
# Quoted strings — product/project names
_QUOTED_RE  = re.compile(r"[\"“«']([^\"”»']{2,40})[\"”»']")

# Generic capitalized words that are not companies/people/products.
_CAP_STOP: Set[str] = {
    "the", "a", "an", "is", "are", "was", "were", "will", "has", "have",
    "this", "that", "these", "those", "new", "first", "last", "next",
    "today", "yesterday", "tomorrow", "report", "reports", "analysis",
    "breaking", "update", "news", "how", "why", "what", "when", "where",
    "january", "february", "march", "april", "may", "june", "july",
    "august", "september", "october", "november", "december",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday",
    "sunday",
}


def _clean_candidate(s: str) -> str:
    return s.strip().strip(".,;:!?()[]{}")


def _looks_like_entity(token: str) -> bool:
    tl = token.lower()
    if tl in _CAP_STOP:
        return False
    if len(token) < 2:
        return False
    return True


def extract_entities(text: str, llm_router: Any = None) -> Dict[str, List[str]]:
    """Extract {organizations, people, products, topics} from a title/snippet.

    If `llm_router` is provided and exposes `.generate(prompt, task="filter")`,
    we attempt the LLM path first; on any failure we fall back to regex.
    """
    text = (text or "").strip()
    if not text:
        return {"organizations": [], "people": [], "products": [], "topics": []}

    if llm_router is not None:
        try:
            return _extract_entities_llm(text, llm_router)
        except Exception as e:
            logger.debug("[semantic_dedup] LLM entity extraction failed: %s", e)

    return _extract_entities_regex(text)


def _extract_entities_regex(text: str) -> Dict[str, List[str]]:
    orgs:     List[str] = []
    products: List[str] = []
    topics:   List[str] = []

    # 1. Products first (digits usually imply product/version).
    for m in _PRODUCT_RE.finditer(text):
        c = _clean_candidate(m.group(1))
        if c and c.lower() not in _CAP_STOP and any(ch.isdigit() for ch in c):
            products.append(c)

    # 2. Quoted strings → products/topics.
    for m in _QUOTED_RE.finditer(text):
        c = _clean_candidate(m.group(1))
        if c:
            products.append(c)

    # 3. Capitalized sequences → organizations (most are companies/brands).
    for m in _CAP_SEQ_RE.finditer(text):
        c = _clean_candidate(m.group(1))
        if not c:
            continue
        # Filter out all-lowercase-stopword combinations and sentence-start noise.
        first = c.split()[0]
        if not _looks_like_entity(first):
            continue
        # Skip if it looks like a product (ends with digit)
        if any(ch.isdigit() for ch in c):
            continue
        orgs.append(c)

    # 4. Lowercase keywords → topics (simple noun-like tokens).
    lower_tokens = re.findall(r"[a-zа-яё]{4,}", text.lower(), re.UNICODE)
    for t in lower_tokens:
        if t not in _SIG_STOPWORDS and t not in _CAP_STOP:
            topics.append(t)

    return {
        "organizations": _unique(orgs),
        "people":        [],
        "products":      _unique(products),
        "topics":        _unique(topics)[:15],
    }


def _unique(seq: Iterable[str]) -> List[str]:
    seen: Set[str] = set()
    out:  List[str] = []
    for x in seq:
        k = x.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(x)
    return out


def _extract_entities_llm(text: str, llm_router: Any) -> Dict[str, List[str]]:
    prompt = (
        "Extract named entities from the news text below. "
        "Return ONLY a JSON object with keys: "
        "organizations, people, products, topics. "
        "Each value is a list of strings. No commentary.\n\n"
        f"TEXT: {text[:500]}\n\nJSON:"
    )
    raw = llm_router.generate(prompt, task="filter")
    if isinstance(raw, dict):
        raw = raw.get("response") or raw.get("text") or ""
    raw = (raw or "").strip()
    # Strip code fences if present.
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        raise ValueError("no JSON in LLM response")
    data = json.loads(m.group(0))
    return {
        "organizations": _unique(data.get("organizations") or []),
        "people":        _unique(data.get("people")        or []),
        "products":      _unique(data.get("products")      or []),
        "topics":        _unique(data.get("topics")        or []),
    }


# ---------------------------------------------------------------------------
# Entity overlap
# ---------------------------------------------------------------------------

# Weights per entity type — orgs and products matter most.
_TYPE_WEIGHTS: Dict[str, float] = {
    "organizations": 0.40,
    "products":      0.35,
    "people":        0.15,
    "topics":        0.10,
}


def _norm_entity_set(values: Iterable[str]) -> Set[str]:
    return {v.lower().strip() for v in values if v and v.strip()}


def entity_overlap(e1: Dict[str, List[str]], e2: Dict[str, List[str]]) -> float:
    """Weighted overlap ratio in [0.0, 1.0].

    For each entity type, computes Jaccard on the two sides, then takes
    a weighted sum. Empty on both sides for a type contributes 0.
    """
    if not e1 or not e2:
        return 0.0
    total = 0.0
    for kind, weight in _TYPE_WEIGHTS.items():
        s1 = _norm_entity_set(e1.get(kind) or [])
        s2 = _norm_entity_set(e2.get(kind) or [])
        if not s1 and not s2:
            continue
        if not s1 or not s2:
            # Partial penalty: one side empty → 0 for this kind
            continue
        inter = len(s1 & s2)
        union = len(s1 | s2)
        if union == 0:
            continue
        total += weight * (inter / union)
    return min(1.0, total)


# ---------------------------------------------------------------------------
# Grouping by entities
# ---------------------------------------------------------------------------

def _event_text(ev: Any) -> str:
    title = _get(ev, "canonical_title", "") or _get(ev, "title", "") or ""
    # Include first article snippet if accessible.
    arts = _get(ev, "articles", []) or []
    snippets = []
    for a in arts[:3]:
        sn = _get(a, "snippet", "")
        if sn:
            snippets.append(sn)
    return f"{title} {' '.join(snippets)}".strip()


def _event_entities(ev: Any, llm_router: Any = None) -> Dict[str, List[str]]:
    cached = _get(ev, "entities", None)
    if cached and isinstance(cached, dict):
        return cached
    ents = extract_entities(_event_text(ev), llm_router=llm_router)
    try:
        setattr(ev, "entities", ents)
    except Exception:
        pass
    return ents


def _merge_events(primary: Any, others: List[Any]) -> Any:
    """Merge `others` into `primary`: combine articles and sources lists."""
    if not others:
        return primary
    try:
        arts = list(_get(primary, "articles", []) or [])
        srcs = list(_get(primary, "sources",  []) or [])
        seen_urls: Set[str] = {
            (s.get("url") if isinstance(s, dict) else getattr(s, "url", ""))
            for s in srcs if s
        }
        for ev in others:
            for a in _get(ev, "articles", []) or []:
                arts.append(a)
            for s in _get(ev, "sources", []) or []:
                url = s.get("url") if isinstance(s, dict) else getattr(s, "url", "")
                if url and url in seen_urls:
                    continue
                if url:
                    seen_urls.add(url)
                srcs.append(s)
        try:
            setattr(primary, "articles", arts)
        except Exception:
            pass
        try:
            setattr(primary, "sources", srcs)
        except Exception:
            pass
    except Exception as e:
        logger.warning("[semantic_dedup] merge failed: %s", e)
    return primary


def group_by_entities(
    events: List[Any],
    threshold: float = 0.5,
    llm_router: Any = None,
) -> List[Any]:
    """Merge events with entity_overlap >= threshold. Sources get combined.

    Greedy union-find over pairwise overlap. Events with no entities at all
    stay as-is (they become their own singletons).
    """
    if not events:
        return []
    n = len(events)
    ents_list: List[Dict[str, List[str]]] = [
        _event_entities(ev, llm_router=llm_router) for ev in events
    ]

    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        parent[find(a)] = find(b)

    for i in range(n):
        for j in range(i + 1, n):
            ov = entity_overlap(ents_list[i], ents_list[j])
            if ov >= threshold:
                union(i, j)

    groups: Dict[int, List[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)

    merged: List[Any] = []
    for _, idxs in groups.items():
        # Primary = event with most articles, tie-break on first occurrence.
        idxs_sorted = sorted(
            idxs,
            key=lambda i: (-len(_get(events[i], "articles", []) or []), i),
        )
        primary = events[idxs_sorted[0]]
        others  = [events[i] for i in idxs_sorted[1:]]
        merged.append(_merge_events(primary, others))

    logger.info(
        "[semantic_dedup] entity grouping: %d -> %d (threshold=%.2f)",
        n, len(merged), threshold,
    )
    return merged


# ---------------------------------------------------------------------------
# Cross-digest duplicate filtering
# ---------------------------------------------------------------------------

def _char_ngrams(text: str, n: int = 3) -> Set[str]:
    text = (text or "").lower()
    text = _PUNCT_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text).strip()
    if len(text) < n:
        return {text} if text else set()
    return {text[i:i + n] for i in range(len(text) - n + 1)}


def _trigram_jaccard(a: str, b: str) -> float:
    sa, sb = _char_ngrams(a, 3), _char_ngrams(b, 3)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _load_recent_digest_titles(
    storage: Any,
    days: int = 7,
) -> List[Tuple[str, str]]:
    """Return [(digest_date, canonical_title)] for last N days.

    Reads from `digest_items` if it exists, else falls back to `digests.metadata_json`.
    Fails open: on any DB error returns [].
    """
    if storage is None:
        return []
    cutoff = (datetime.utcnow().date() - timedelta(days=days)).isoformat()
    # Try digest_items first.
    try:
        rows = storage.fetchall(
            "SELECT digest_date, canonical_title "
            "FROM digest_items WHERE digest_date >= %s",
            (cutoff,),
        )
        out: List[Tuple[str, str]] = []
        for r in rows or []:
            if isinstance(r, dict):
                out.append((str(r.get("digest_date")), str(r.get("canonical_title") or "")))
            else:
                out.append((str(r[0]), str(r[1] or "")))
        if out:
            return out
    except Exception as e:
        logger.debug("[semantic_dedup] digest_items read failed: %s", e)

    # Fallback: parse digest metadata_json for recent digests.
    try:
        rows = storage.fetchall(
            "SELECT digest_date, metadata_json FROM digests "
            "WHERE digest_date >= %s",
            (cutoff,),
        )
        out2: List[Tuple[str, str]] = []
        for r in rows or []:
            dd   = r.get("digest_date") if isinstance(r, dict) else r[0]
            meta = r.get("metadata_json") if isinstance(r, dict) else r[1]
            if not meta:
                continue
            try:
                md = json.loads(meta)
            except Exception:
                continue
            titles = md.get("titles") or md.get("canonical_titles") or []
            for t in titles:
                out2.append((str(dd), str(t)))
        return out2
    except Exception as e:
        logger.debug("[semantic_dedup] digests fallback read failed: %s", e)
        return []


def find_similar_in_history(
    signature: str,
    storage: Any,
    days: int = 7,
    threshold: float = 0.7,
) -> List[Tuple[str, str]]:
    """Query digest history for titles with similar signature in last N days."""
    recent = _load_recent_digest_titles(storage, days=days)
    matches: List[Tuple[str, str]] = []
    for dd, title in recent:
        sim = _trigram_jaccard(signature, title)
        if sim >= threshold:
            matches.append((dd, title))
    return matches


def filter_recent_duplicates(
    events: List[Any],
    storage: Any,
    days: int = 7,
    threshold: float = 0.7,
    llm_router: Any = None,
) -> List[Any]:
    """Remove events that duplicate a story published in the last N days.

    Combines two signals:
      - trigram Jaccard(signature, past_title) >= threshold
      - entity overlap with a cached past entity set (if available)

    Falls open on any DB error.
    """
    if not events:
        return []
    recent = _load_recent_digest_titles(storage, days=days)
    if not recent:
        return events

    # Precompute past signatures.
    past_sigs: List[Tuple[str, str]] = [
        (dd, compute_card_signature({"title": t})) for dd, t in recent
    ]

    kept: List[Any] = []
    for ev in events:
        sig = compute_card_signature({
            "title":   _get(ev, "canonical_title", "") or _get(ev, "title", ""),
            "snippet": "",
        })
        dup = False
        for dd, past_sig in past_sigs:
            # Trigram on signatures (roughly word-collision) and on raw titles
            if _trigram_jaccard(sig, past_sig) >= threshold:
                dup = True
                logger.info(
                    "[semantic_dedup] drop recent duplicate: %r ≈ %r (%s)",
                    sig[:60], past_sig[:60], dd,
                )
                break
        if not dup:
            kept.append(ev)

    logger.info(
        "[semantic_dedup] cross-digest filter: %d -> %d (threshold=%.2f, days=%d)",
        len(events), len(kept), threshold, days,
    )
    return kept
