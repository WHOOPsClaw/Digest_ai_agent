"""digest/composer.py — assemble final digest issue from synthesized events.

Entry point:
    compose_digest_issue(items_by_category, issue_date, issue_time, issue_name)
        → DigestIssue

Output format: Telegram HTML (parse_mode="HTML")

────────────────────────────────────────────────────────────────────────────
Example output (one Telegram message)
────────────────────────────────────────────────────────────────────────────

    📰 УТРЕННИЙ ДАЙДЖЕСТ
    13 апреля 2026


    ⚡ Главное

    • Nebius ведёт переговоры о покупке AI21 Labs — стартап оценивается в $1.4 млрд
    • Москва запускает беспилотные такси — 50 автомобилей в тестовом режиме
    • ...


    🤖 AI и нейросети

    Nebius переговоры с AI21 Labs
    Суть события.
    Почему важно: Рост консолидации в ИИ-отрасли.
    Редакция: Стратегический шаг для усиления позиций.
    🔗 rbc.ru · habr.com

    · · ·

    Второе событие
    ...

────────────────────────────────────────────────────────────────────────────
Telegram split
────────────────────────────────────────────────────────────────────────────
Section separator: triple newline  (\\n\\n\\n)  — between header/главное/categories
Item separator:    "· · ·"         (\\n\\n· · ·\\n\\n) — between cards within a category
"""

from __future__ import annotations

import html
import logging
import re
from dataclasses import dataclass, field
from datetime import date as _date
from typing import Dict, List, Optional
from urllib.parse import urlparse

from newsbrief.processing.synthesizer import SynthesizedItem

logger = logging.getLogger("uvicorn.error")


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TELEGRAM_MAX_LEN = 3800

CATEGORY_ORDER: List[str] = ["world", "russia_moscow", "ai_agents", "tech", "ai", "games"]

CATEGORY_NAMES: Dict[str, str] = {
    "world":         "Мировые новости",
    "russia_moscow": "Россия и Москва",
    "ai":            "AI и нейросети",
    "games":         "Игры",
    "ai_agents":     "AI-агенты и инструменты",
    "tech":          "Технологии",
    # backward compat
    "moscow":        "Москва",
}

CATEGORY_EMOJI: Dict[str, str] = {
    "world":         "🌍",
    "russia_moscow": "🇷🇺",
    "ai":            "🤖",
    "games":         "🎮",
    "ai_agents":     "🧠",
    "tech":          "💻",
    # backward compat
    "moscow":        "🏙",
}

_RU_MONTHS: Dict[int, str] = {
    1: "января",  2: "февраля",  3: "марта",   4: "апреля",
    5: "мая",     6: "июня",     7: "июля",     8: "августа",
    9: "сентября",10: "октября", 11: "ноября",  12: "декабря",
}

# Visual separators — plain text, safe inside Telegram HTML
_SECTION_SEP = "\n\n\n"            # triple newline between major sections
_ITEM_SEP    = "\n\n· · ·\n\n"    # between items within a category block


# ---------------------------------------------------------------------------
# Output dataclass
# ---------------------------------------------------------------------------

@dataclass
class DigestIssue:
    full_text:       str
    telegram_parts:  List[str]
    headline_items:  List[str]
    category_blocks: Dict[str, str]
    item_count:      int
    metadata:        dict


# ---------------------------------------------------------------------------
# Date formatting (no locale dependency)
# ---------------------------------------------------------------------------

def _format_ru_date(d: _date) -> str:
    return f"{d.day} {_RU_MONTHS[d.month]} {d.year}"


# ---------------------------------------------------------------------------
# HTML helpers
# ---------------------------------------------------------------------------

def _esc(text: str) -> str:
    """HTML-escape text for Telegram HTML mode."""
    return html.escape(text) if text else ""


def _source_domain(url: str) -> str:
    """Extract clean domain from URL, e.g. 'bbc.co.uk'."""
    try:
        netloc = urlparse(url).netloc
        return netloc.replace("www.", "") or url[:25]
    except Exception:
        return url[:25]


def _format_sources(sources: List[dict], max_sources: int = 3) -> str:
    """Build a compact source-links line for a card.

    Prefers RSS sources (specific articles) over search sources (tag pages).
    Deduplicates by domain. Returns empty string if no valid sources.
    """
    if not sources:
        return ""

    rss    = [s for s in sources if s.get("source") == "rss" and s.get("url")]
    search = [s for s in sources if s.get("source") != "rss" and s.get("url")]
    ordered = (rss + search)[:max_sources * 2]  # oversample, dedup by domain

    links: List[str] = []
    seen_domains: set = set()
    for s in ordered:
        url = s.get("url", "")
        if not url:
            continue
        domain = _source_domain(url)
        if domain in seen_domains:
            continue
        seen_domains.add(domain)
        links.append(f'<a href="{_esc(url)}">{_esc(domain)}</a>')
        if len(links) >= max_sources:
            break

    return ("🔗 " + " · ".join(links)) if links else ""


def _first_sentence(text: str, max_chars: int = 120) -> str:
    """Return first sentence of text, capped at max_chars."""
    if not text:
        return ""
    m = re.search(r"[.!?](?:\s|$)", text)
    if m:
        return text[:m.end()].strip()[:max_chars]
    return text[:max_chars].rstrip()


# ---------------------------------------------------------------------------
# Item scoring (for headline selection)
# ---------------------------------------------------------------------------

def _item_score(item: SynthesizedItem) -> int:
    score = 0
    if item.llm_used:                              score += 2
    if item.why_it_matters:                        score += 1
    if item.editor_take:                           score += 1
    if item.summary_ru and len(item.summary_ru) > 80: score += 1
    return score


# ---------------------------------------------------------------------------
# Headline block
# ---------------------------------------------------------------------------

def compose_headline_block(top_items: List[SynthesizedItem]) -> str:
    """Format 2–4 top items as the '⚡ Главное' overview block."""
    if not top_items:
        return ""

    lines = ["⚡ <b>Главное</b>", ""]
    for item in top_items:
        first     = _first_sentence(item.summary_ru)
        title_esc = _esc(item.title)
        if first and first.rstrip(".!?") != item.title.rstrip(".!?"):
            lines.append(f"• <b>{title_esc}</b> — {_esc(first)}")
        else:
            lines.append(f"• <b>{title_esc}</b>")

    return "\n".join(lines)


def _select_headline_items(
    items_by_category: Dict[str, List[SynthesizedItem]],
    count: int = 4,
) -> List[SynthesizedItem]:
    """Pick the strongest items for the headline block.

    When items carry ranking scores (final_score > 0, set by ranker.py),
    world events are scored by global_importance_score to give a "world top"
    feel.  Fallback: legacy _item_score heuristic.

    Caps: up to 3 world events (global top), up to 2 from other categories.
    """
    def _headline_score(item: SynthesizedItem, cat: str) -> float:
        if getattr(item, "final_score", 0.0) > 0.0:
            # Ranked mode: world events scored by global importance
            if cat == "world":
                return getattr(item, "global_importance_score", 0.0) + 0.1
            # Other categories: personal relevance + small fraction of global
            return (getattr(item, "personal_relevance_score", 0.0) * 0.7
                    + getattr(item, "global_importance_score", 0.0) * 0.3)
        return float(_item_score(item))

    scored: List[tuple] = [
        (_headline_score(item, cat), cat, item)
        for cat in CATEGORY_ORDER
        for item in items_by_category.get(cat, [])
    ]
    scored.sort(key=lambda x: -x[0])

    seen_cats: Dict[str, int] = {}
    selected: List[SynthesizedItem] = []
    for _score, cat, item in scored:
        # Allow up to 3 world events (for global top feel), 2 for others
        cap = 3 if cat == "world" else 2
        if seen_cats.get(cat, 0) >= cap:
            continue
        selected.append(item)
        seen_cats[cat] = seen_cats.get(cat, 0) + 1
        if len(selected) >= count:
            break

    # Guarantee at least 2 items
    if len(selected) < 2:
        for cat in CATEGORY_ORDER:
            for item in items_by_category.get(cat, []):
                if item not in selected:
                    selected.append(item)
                if len(selected) >= 2:
                    break
            if len(selected) >= 2:
                break

    return selected


# ---------------------------------------------------------------------------
# Item card
# ---------------------------------------------------------------------------

_CARD_STYLE: str = "medium"   # set by compose_digest_issue from config


def _compose_item_card(item: SynthesizedItem) -> str:
    """Format one SynthesizedItem as a compact HTML card.

    Respects _CARD_STYLE:
      brief    — title + 1-line summary only
      medium   — title + summary + why_it_matters  (default)
      detailed — medium + editor_take (if set)
    """
    style = (_CARD_STYLE or "medium").lower()
    lines = [f"<b>{_esc(item.title)}</b>"]

    if style == "brief":
        # Keep to a single short line of summary
        if item.summary_ru:
            lines.append(_esc(_first_sentence(item.summary_ru, max_chars=160)))
        sources_line = _format_sources(item.sources, max_sources=1)
        if sources_line:
            lines.append(sources_line)
        return "\n".join(lines)

    if item.summary_ru:
        lines.append(_esc(item.summary_ru))

    if item.why_it_matters:
        lines.append(f"<blockquote><i>Почему важно:</i> {_esc(item.why_it_matters)}</blockquote>")

    if style == "detailed" and getattr(item, "editor_take", ""):
        lines.append(f"<i>Редакция:</i> {_esc(item.editor_take)}")

    sources_line = _format_sources(item.sources)
    if sources_line:
        lines.append(sources_line)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Category block
# ---------------------------------------------------------------------------



_CONFIDENCE_BADGE: dict = {}


def _compose_ai_agents_card(item) -> str:
    """Format ai_agents SynthesizedItem with intelligence layer fields.

    Format:
        [✓] <b>Заголовок</b>
        Что произошло.
        <i>Почему важно:</i> ...
        <i>Зона влияния:</i> coding agents, MCP
        🔗 sources
    """
    badge = _CONFIDENCE_BADGE.get(item.confidence, "")
    prefix = f"{badge} " if badge else ""
    lines_out = [f"{prefix}<b>{_esc(item.title)}</b>"]

    if item.summary_ru:
        lines_out.append(_esc(item.summary_ru))

    if item.why_it_matters:
        lines_out.append(f"<blockquote><i>Почему важно:</i> {_esc(item.why_it_matters)}</blockquote>")

    if getattr(item, "affected_area", ""):
        lines_out.append(f"<i>Зона влияния:</i> {_esc(item.affected_area)}")

    sources_line = _format_sources(item.sources)
    if sources_line:
        lines_out.append(sources_line)

    return "\n".join(lines_out)
def compose_category_block(category: str, items: List[SynthesizedItem]) -> str:
    """Format all items for one category with an emoji header."""
    if not items:
        return ""

    name   = CATEGORY_NAMES.get(category, category.upper())
    emoji  = CATEGORY_EMOJI.get(category, "")
    header = f"{emoji} <b>{_esc(name)}</b>"
    body   = _ITEM_SEP.join(_compose_ai_agents_card(item) if item.category == "ai_agents" else _compose_item_card(item) for item in items)
    return f"{header}\n\n{body}"


# ---------------------------------------------------------------------------
# Radar block
# ---------------------------------------------------------------------------

def _compose_radar_block(radar_items: List[SynthesizedItem]) -> str:
    if not radar_items:
        return ""

    lines = ["📡 <b>На радаре</b>", ""]
    for item in radar_items:
        first = _first_sentence(item.summary_ru)
        line  = f"• <b>{_esc(item.title)}</b>"
        if first and first.rstrip(".!?") != item.title.rstrip(".!?"):
            line += f" — {_esc(first)}"
        lines.append(line)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Telegram splitter
# ---------------------------------------------------------------------------

def split_digest_for_telegram(
    text: str,
    max_len: int = TELEGRAM_MAX_LEN,
) -> List[str]:
    """Split full digest HTML into Telegram-safe parts.

    Primary split: section boundaries (triple newline → one message per section).
    Secondary: length-based sub-split within oversized sections.
    This ensures each category block goes as its own message when possible.
    """
    # Always split by section boundaries first (each category = one message)
    raw_sections = [s.strip() for s in re.split(r'\n{3,}', text) if s.strip()]
    if not raw_sections:
        return [text.strip()] if text.strip() else []


    parts: List[str] = []
    for section in raw_sections:
        if len(section) <= max_len:
            parts.append(section)
        else:
            parts.extend(_sub_split_section(section, max_len))

    logger.info("[composer] split into %d telegram parts", len(parts))
    return parts


def _sub_split_section(text: str, max_len: int) -> List[str]:
    """Sub-split one section that exceeds max_len, preserving item boundaries."""
    parts: List[str] = []
    remaining = text
    while len(remaining) > max_len:
        chunk    = remaining[:max_len]
        split_at = _best_split_pos(chunk, max_len)
        part     = remaining[:split_at].rstrip()
        remaining = remaining[split_at:].lstrip()
        if part:
            parts.append(part)
    if remaining:
        parts.append(remaining)
    return parts


def _best_split_pos(chunk: str, max_len: int) -> int:
    # 1. Item separator (· · ·)
    pos = chunk.rfind(_ITEM_SEP)
    if pos > max_len // 4:
        return pos + len(_ITEM_SEP)

    # 2. Double newline
    pos = chunk.rfind("\n\n")
    if pos > max_len // 5:
        return pos + 2

    # 3. Single newline
    pos = chunk.rfind("\n")
    if pos > 0:
        return pos + 1

    return max_len


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def compose_digest_issue(
    items_by_category: Dict[str, List[SynthesizedItem]],
    issue_date: _date,
    issue_time: str = "10:00",
    issue_name: str = "Утренний дайджест",
    radar_items: Optional[List[SynthesizedItem]] = None,
    card_style: Optional[str] = None,
) -> DigestIssue:
    """Assemble a complete digest issue from synthesized category items.

    Output structure (each section = one Telegram message, with hashtag):
      1. Header + ⚡ Главное (top 5 bullets)          → #главное #world
      2. 🌍 Мировые новости (up to 5 full cards)      → #world
      3. 🇷🇺 Россия и Москва (up to 5 cards)          → #Москва
      4. 🤖 AI и технологии (top 5 from ai/ai_agents/tech merged) → #ai
      5. 🎮 Игры (up to 5 cards)                      → #games

    Sections are separated by triple newline (_SECTION_SEP).
    split_digest_for_telegram() will produce one message per section,
    with sub-splitting only when a section exceeds TELEGRAM_MAX_LEN.
    """
    radar_items = radar_items or []

    # Apply card style for this render
    global _CARD_STYLE
    if card_style:
        _CARD_STYLE = str(card_style).lower()
    else:
        _CARD_STYLE = "medium"

    # --- 1. Header ---
    ru_date = _format_ru_date(issue_date)
    header  = f"📰 <b>{_esc(issue_name).upper()}</b>\n{ru_date}"

    # --- 2. Headline block (top 5 from all categories) ---
    headline_candidates = _select_headline_items(items_by_category, count=5)
    headline_block      = compose_headline_block(headline_candidates)
    headline_lines      = [l for l in headline_block.splitlines() if l.startswith("•")]

    # --- Section 1: Главное ---
    sec1_body = "\n\n".join(filter(None, [header, headline_block]))
    sec1      = sec1_body + "\n\n#главное #world"

    # --- Section 2: Мировые новости ---
    world_items = items_by_category.get("world", [])[:5]
    if world_items:
        world_body = _ITEM_SEP.join(_compose_item_card(i) for i in world_items)
        sec_world  = f"🌍 <b>Мировые новости</b>\n#world\n\n{world_body}"
    else:
        sec_world = ""

    # --- Section 3: Россия и Москва ---
    moscow_items = items_by_category.get("russia_moscow", [])[:5]
    if moscow_items:
        moscow_body = _ITEM_SEP.join(_compose_item_card(i) for i in moscow_items)
        sec_moscow  = f"🇷🇺 <b>Россия и Москва</b>\n#Москва\n\n{moscow_body}"
    else:
        sec_moscow = ""

    # --- Section 4: AI и технологии (merged ai + ai_agents + tech, top 5) ---
    ai_pool: List[SynthesizedItem] = []
    for cat in ["ai_agents", "ai", "tech"]:
        ai_pool.extend(items_by_category.get(cat, []))

    def _ai_sort_key(item: SynthesizedItem) -> float:
        fs = getattr(item, "final_score", 0.0)
        return -fs if fs > 0.0 else float(-_item_score(item))

    ai_pool.sort(key=_ai_sort_key)
    ai_items = ai_pool[:5]
    if ai_items:
        ai_body = _ITEM_SEP.join(
            _compose_ai_agents_card(i) if i.category == "ai_agents" else _compose_item_card(i)
            for i in ai_items
        )
        sec_ai = f"🤖 <b>AI и технологии</b>\n#ai\n\n{ai_body}"
    else:
        sec_ai = ""

    # --- Section 5: Игры ---
    games_items = items_by_category.get("games", [])[:5]
    if games_items:
        games_body = _ITEM_SEP.join(_compose_item_card(i) for i in games_items)
        sec_games  = f"🎮 <b>Игры</b>\n#games\n\n{games_body}"
    else:
        sec_games = ""

    # --- Assemble ---
    all_sections = [sec1] + [s for s in [sec_world, sec_moscow, sec_ai, sec_games] if s]
    full_text    = _SECTION_SEP.join(all_sections)

    # --- Split for Telegram ---
    telegram_parts = split_digest_for_telegram(full_text)

    # --- category_blocks: keep for backward compat metadata ---
    category_blocks: Dict[str, str] = {}
    for cat, sec in [("world", sec_world), ("russia_moscow", sec_moscow),
                     ("ai", sec_ai), ("games", sec_games)]:
        if sec:
            category_blocks[cat] = sec

    # --- Metadata ---
    total_items = sum(len(v) for v in items_by_category.values())
    metadata = {
        "date":               str(issue_date),
        "time":               issue_time,
        "issue_name":         issue_name,
        "categories_present": [c for c in CATEGORY_ORDER if items_by_category.get(c)],
        "has_radar":          False,
        "llm_items":          sum(
            1 for items in items_by_category.values()
            for item in items if item.llm_used
        ),
        "fallback_items":     sum(
            1 for items in items_by_category.values()
            for item in items if not item.llm_used
        ),
    }

    logger.info(
        "[composer] issue assembled: items=%d sections=%d parts=%d cats=%s",
        total_items,
        len(all_sections),
        len(telegram_parts),
        metadata["categories_present"],
    )

    return DigestIssue(
        full_text=      full_text,
        telegram_parts= telegram_parts,
        headline_items= headline_lines,
        category_blocks=category_blocks,
        item_count=     total_items,
        metadata=       metadata,
    )
