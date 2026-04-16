"""digest/synthesizer.py — LLM-based synthesis of DigestEvents into editorial cards.

Main entry point:
    synthesize_category_digest(events, max_events=5, user_id=None) -> List[SynthesizedItem]

LLM pipeline: POST AI_WORKER_URL/llm/generate (same as main.py).
Parallel processing: ThreadPoolExecutor with DIGEST_PARALLEL_WORKERS (default 2).

Fallback guarantees:
  - LLM unreachable / timeout    → raw snippets (translated to Russian if needed)
  - Response unparseable          → same fallback
  - Partial parse (missing field) → fill gap from fallback, keep the rest
  - summary not in Russian        → short LLM translate call, then original if that fails

────────────────────────────────────────────────────────────────────────────
Prompt template (see build_event_prompt docstring for full text)
────────────────────────────────────────────────────────────────────────────
Ты опытный новостной редактор. Пишешь аналитическую карточку для умного читателя.

СОБЫТИЕ:
Заголовки:
- OpenAI confirms GPT-5 enterprise launch
- OpenAI GPT-5 pricing details revealed

Фрагменты:
- OpenAI announced the release targeting enterprise customers...

[Контекст предыдущих событий:]   ← только если user_id задан и есть релевантная память
- OpenAI: ...

ИНСТРУКЦИИ:
1. НЕ пересказывай источники — выдели суть
2. Если это продолжение известной темы — явно укажи
3. Если новость не несёт новой информации — назови это слабым сигналом
...

ФОРМАТ (строго):
[ЗАГОЛОВОК]
[СУТЬ]
[ПОЧЕМУ ВАЖНО]
[РЕДАКЦИОННЫЙ КОММЕНТАРИЙ]

────────────────────────────────────────────────────────────────────────────
Parser: safe_extract(section_name, text)
────────────────────────────────────────────────────────────────────────────
Each section is extracted independently — missing one section does not
invalidate the others. Result is None only when BOTH title AND summary
are absent (= no useful content at all).

Example — partial parse (title missing, summary present):
  Input:  "[СУТЬ]\\nOpenAI выпустила GPT-5.\\n[ПОЧЕМУ ВАЖНО]\\nВажно."
  Result: title="" (filled from fallback), summary_ru="OpenAI выпустила GPT-5."
          _partial=True → logged as warning

────────────────────────────────────────────────────────────────────────────
Fallback scenario example
────────────────────────────────────────────────────────────────────────────
Event articles:
  1. title="OpenAI releases GPT-5"   snippet="OpenAI launched GPT-5 enterprise..."
  2. title="GPT-5 launch confirmed"  snippet="Pricing starts at $30 per million tokens..."

LLM unreachable → _build_fallback:
  title:         "OpenAI releases GPT-5"   (canonical_title)
  summary_ru:    "OpenAI launched GPT-5 enterprise... Pricing starts at $30..."
                 → _is_mostly_russian = False → _translate_to_russian called
                 → "OpenAI запустила GPT-5 для enterprise... Цена — $30 за млн токенов."
  why_it_matters: ""
  editor_take:    ""
  llm_used:       False

────────────────────────────────────────────────────────────────────────────
Timing (approximate, local Ollama model ~60s/call)
────────────────────────────────────────────────────────────────────────────
Before (sequential, 5 events): ~5 × 60s = 5 min
After  (parallel workers=2):   ~3 × 60s = 3 min  (ceil(5/2) rounds)
"""

from __future__ import annotations

import os
import re
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Dict, List, Optional

import httpx
# psycopg2 imported lazily when needed
# db_pool imported lazily when needed

from .events import DigestEvent

logger = logging.getLogger("uvicorn.error")


# ---------------------------------------------------------------------------
# Config — mirrors main.py env vars
# ---------------------------------------------------------------------------

AI_WORKER_URL         = os.getenv("AI_WORKER_URL",          "http://100.122.206.49:8001")
AI_WORKER_TIMEOUT     = float(os.getenv("AI_WORKER_TIMEOUT", "120"))
DIGEST_LLM_MODEL      = os.getenv("DIGEST_LLM_MODEL",       "main_local")
DIGEST_PARALLEL_WORKERS = int(os.getenv("DIGEST_PARALLEL_WORKERS", "2"))
DIGEST_MEMORY_TOP_K   = int(os.getenv("DIGEST_MEMORY_TOP_K", "3"))

# Prompt content limits
_MAX_TITLES    = 5
_MAX_SNIPPETS  = 4
_SNIPPET_CHARS = 250


# ---------------------------------------------------------------------------
# Output type
# ---------------------------------------------------------------------------

@dataclass
class SynthesizedItem:
    category:        str
    title:           str
    summary_ru:      str
    why_it_matters:  str
    editor_take:     str
    sources:         List[dict]       # forwarded from DigestEvent.sources
    published_at:    Optional[str]    # ISO string or None
    llm_used:        bool             # False = fallback path
    affected_area:   str = ""         # e.g. "coding agents, MCP, browser tools"
    confidence:      str = ""         # "verified" | "partially_verified" | "signal_only"
    # Ranking scores from ranker.py (0.0 = not ranked / legacy)
    global_importance_score:  float = 0.0
    personal_relevance_score: float = 0.0
    final_score:              float = 0.0


# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------

_CYRILLIC_RE = re.compile(r"[а-яёА-ЯЁ]")
_ALPHA_RE    = re.compile(r"[a-zA-Zа-яёА-ЯЁ]")


def _is_mostly_russian(text: str) -> bool:
    """True if Cyrillic chars are >40% of all alphabetic chars."""
    cyrillic = len(_CYRILLIC_RE.findall(text))
    total    = len(_ALPHA_RE.findall(text))
    return total == 0 or (cyrillic / total) > 0.40


# ---------------------------------------------------------------------------
# DB connection (mirrors storage.py — intentionally duplicated, no main.py import)
# ---------------------------------------------------------------------------

# Connection pool — see db_pool.py


# ---------------------------------------------------------------------------
# Memory context
# ---------------------------------------------------------------------------

def _fetch_memory_context(user_id: str, query: str) -> str:
    """Search memory_items for relevant past context. Returns formatted block or "".

    Uses keyword ILIKE search — same approach as main.py:_search_memory_items,
    but inlined here to avoid importing main.py. Excludes digest-type entries
    (type='digest') to prevent circular self-reference.
    """
    if not user_id or not query:
        return ""

    words = list(dict.fromkeys(
        w for w in re.findall(r"[а-яёА-ЯЁa-zA-Z]{3,}", query.lower())
    ))[:6]
    if not words:
        return ""

    try:
        with get_conn() as conn:
            cur  = conn.cursor()
            conds = " OR ".join(
                "(LOWER(title) LIKE %s OR LOWER(content) LIKE %s)" for _ in words
            )
            params: list = []
            for w in words:
                params.extend([f"%{w}%", f"%{w}%"])
            params.extend([user_id, DIGEST_MEMORY_TOP_K])
            cur.execute(
                f"""SELECT title, content
                    FROM memory_items
                    WHERE ({conds})
                      AND user_id = %s
                      AND type != 'digest'
                    ORDER BY importance DESC, created_at DESC
                    LIMIT %s""",
                params,
            )
            rows = cur.fetchall()
            cur.close()
    except Exception as e:
        logger.warning("[synthesizer] memory fetch failed: %s", e)
        return ""

    if not rows:
        return ""

    lines = []
    for title, content in rows:
        snippet = (content or "")[:150].strip()
        lines.append(f"- {title}: {snippet}" if snippet else f"- {title}")

    return "Контекст предыдущих событий:\n" + "\n".join(lines)


def _fetch_user_profile(user_id: str) -> str:
    """Load all type='user' memory items as a profile string for prompt injection.

    Called ONCE per digest run (not per event). Returns "" if no profile saved.
    """
    if not user_id:
        return ""
    try:
        with get_conn() as conn:
            cur  = conn.cursor()
            cur.execute(
                """SELECT title, content FROM memory_items
                   WHERE user_id = %s AND type = 'user'
                   ORDER BY importance DESC, created_at DESC
                   LIMIT 30""",
                (user_id,),
            )
            rows = cur.fetchall()
            cur.close()
    except Exception as e:
        logger.warning("[synthesizer] profile fetch failed: %s", e)
        return ""

    if not rows:
        return ""

    lines = []
    for title, content in rows:
        body = (content or "").strip()
        if body:
            lines.append(f"- {body}")
        elif title:
            lines.append(f"- {title}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Parser helpers
# ---------------------------------------------------------------------------

_SECTION_NAMES = ["ЗАГОЛОВОК", "СУТЬ", "ПОЧЕМУ ВАЖНО", "РЕДАКЦИОННЫЙ КОММЕНТАРИЙ"]

# Fallback profile used in digest prompt when no user profile is saved in DB
_DEFAULT_USER_PROFILE = (
    "Разработчик, строит личную AI-инфраструктуру. "
    "Интересы: AI/LLM и их практическое применение, технологии и продукты, "
    "игровая индустрия, события в Москве и России, мировая геополитика и экономика."
)
_ANY_TAG_PAT   = r"\[(?:" + "|".join(re.escape(s) for s in _SECTION_NAMES) + r")\]"


def safe_extract(section_name: str, text: str) -> str:
    """Extract content of a single [SECTION_NAME] block from LLM response.

    Works independently — does not require other sections to be present.
    Strips echoed format hints like "(до 80 символов, без кавычек)".

    Returns empty string if the section is absent or its content is empty.
    """
    pattern = re.compile(
        r"\[" + re.escape(section_name) + r"\]\s*(.*?)(?=" + _ANY_TAG_PAT + r"|$)",
        re.DOTALL | re.IGNORECASE,
    )
    m = pattern.search(text)
    if not m:
        return ""
    content = m.group(1).strip()
    # Remove echoed hint: "(до 80 символов, без кавычек)" or similar at start
    content = re.sub(r"^\([^)]{3,120}\)\s*", "", content, flags=re.DOTALL).strip()
    return content


def _parse_llm_response(text: str) -> Optional[dict]:
    """Parse structured LLM output into field dict.

    Lenient — extracts sections independently via safe_extract.
    Returns None only when BOTH title AND summary are absent (no useful content).

    Partial results (one required field missing) are returned with _partial=True
    so the caller can fill gaps from fallback data and log a warning.
    """
    # Strip any preamble before [ЗАГОЛОВОК] (LLM sometimes starts with commentary)
    tag_pos = text.find("[ЗАГОЛОВОК]")
    if tag_pos > 0:
        text = text[tag_pos:]

    title   = safe_extract("ЗАГОЛОВОК",               text)
    summary = safe_extract("СУТЬ",                    text)
    why     = safe_extract("ПОЧЕМУ ВАЖНО",            text)
    take    = safe_extract("РЕДАКЦИОННЫЙ КОММЕНТАРИЙ", text)

    if not title and not summary:
        return None   # full fallback needed

    return {
        "title":          title,
        "summary_ru":     summary,
        "why_it_matters": why,
        "editor_take":    take,
        "_partial":       not title or not summary,
    }


# ---------------------------------------------------------------------------
# Translation helper (fallback path)
# ---------------------------------------------------------------------------

def _translate_to_russian(text: str) -> str:
    """Translate text to Russian via LLM. Returns original on any failure."""
    if not text or _is_mostly_russian(text):
        return text
    try:
        with httpx.Client(timeout=min(AI_WORKER_TIMEOUT, 60)) as client:
            resp = client.post(
                f"{AI_WORKER_URL}/llm/generate",
                json={
                    "prompt": (
                        "Переведи на русский кратко и ясно, одним абзацем. "
                        "Верни только перевод, без комментариев.\n\n" + text[:400]
                    ),
                    "model": DIGEST_LLM_MODEL,
                },
            )
            resp.raise_for_status()
            result = resp.json().get("response", "").strip()
            if result and _is_mostly_russian(result):
                logger.info("[synthesizer] fallback translation applied len=%d", len(result))
                return result
    except Exception as e:
        logger.warning("[synthesizer] translation failed: %s", e)
    return text


# ---------------------------------------------------------------------------
# Fallback
# ---------------------------------------------------------------------------

def _build_fallback(event: DigestEvent) -> SynthesizedItem:
    """Build SynthesizedItem from raw snippets without LLM synthesis.

    Guarantees Russian output: translates snippet text if it is not mostly Russian.
    """
    snippets = [
        a.snippet.strip()
        for a in event.articles
        if (a.snippet or "").strip()
    ]
    raw_summary = " ".join(snippets)[:600].strip()

    if raw_summary:
        summary = _translate_to_russian(raw_summary)
        if summary != raw_summary:
            pass  # translation log already emitted by _translate_to_russian
        elif not _is_mostly_russian(summary):
            logger.info("[synthesizer] fallback summary not Russian, translation skipped/failed")
    else:
        summary = event.canonical_title  # last resort
        logger.info("[synthesizer] fallback: no snippets, using canonical_title")

    return SynthesizedItem(
        category=       event.category,
        title=          event.canonical_title,
        summary_ru=     summary,
        why_it_matters= "",
        editor_take=    "",
        sources=        event.sources,
        published_at=   event.published_at.isoformat() if event.published_at else None,
        llm_used=       False,
        confidence=      getattr(event, "role", ""),
    )


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# AI agents intelligence prompt
# ---------------------------------------------------------------------------

_AI_AGENTS_SECTION_NAMES = [
    "ЗАГОЛОВОК", "ЧТО ПРОИЗОШЛО", "ПОЧЕМУ ВАЖНО",
    "ЗОНА ВЛИЯНИЯ", "ДОСТОВЕРНОСТЬ", "ИСТОЧНИКИ",
]
_AI_AGENTS_AFFECTED_AREAS = (
    "coding agents | browser tools | memory | MCP | local LLM | "
    "IDE workflow | orchestration | voice | search | plugins"
)


def build_ai_agents_event_prompt(
    event,
    memory_context: str = "",
    user_profile: str = "",
) -> str:
    """Intelligence-layer prompt for ai_agents category.

    Outputs structured sections for what happened, why it matters,
    affected area, and confidence level.
    """
    from .events import DigestEvent  # noqa: circular-safe (same package)

    titles_seen: set = set()
    titles = []
    for a in event.articles:
        t = (a.title or "").strip()
        if t and t.lower() not in titles_seen:
            titles_seen.add(t.lower())
            titles.append(t)
        if len(titles) >= _MAX_TITLES:
            break

    snippets = []
    for a in event.articles:
        s = (a.snippet or "").strip()
        if s and len(snippets) < _MAX_SNIPPETS:
            snippets.append(s[:_SNIPPET_CHARS])

    # Classify source roles
    roles = [getattr(a, "role", "source") for a in event.articles]
    has_official = "source" in roles
    has_analysis = "analysis" in roles
    confidence_hint = (
        "verified (есть официальный источник)" if has_official
        else "partially_verified (есть аналитика, нет официального источника)" if has_analysis
        else "signal_only (только Telegram/поиск — требует проверки)"
    )
    source_types = ", ".join(sorted(set(roles)))

    titles_block   = "\n".join(f"- {t}" for t in titles)
    snippets_block = "\n".join(f"- {s}" for s in snippets) if snippets else "(нет фрагментов)"
    memory_block   = f"\n{memory_context}\n" if memory_context else ""

    return (
        "Ты аналитик AI-инструментов и агентов. Оцени событие для разработчика, "
        "который строит AI-ассистентов и coding workflows.\n\n"
        "СОБЫТИЕ:\n"
        f"Заголовки:\n{titles_block}\n\n"
        f"Фрагменты:\n{snippets_block}\n"
        f"{memory_block}\n"
        f"Типы источников: {source_types}\n"
        f"Оценка достоверности: {confidence_hint}\n\n"
        "ФИЛЬТР — включай ТОЛЬКО если это реально влияет на:\n"
        "- новые версии AI-ассистентов (Claude Code, Cursor, Windsurf, Copilot, Continue)\n"
        "- новые функции: browser/tools/memory/voice/search/MCP/plugins/IDE/local LLM\n"
        "- новые agent frameworks, MCP servers, tool ecosystems\n"
        "- изменения моделей (context, tool use, reasoning, speed, pricing) с практическим эффектом\n"
        "Если событие не попадает в эти категории — укажи в [ЧТО ПРОИЗОШЛО]: слабый сигнал.\n\n"
        f"ПРОФИЛЬ: {user_profile if user_profile else _DEFAULT_USER_PROFILE}\n\n"
        "ФОРМАТ (строго, только эти теги):\n\n"
        "[ЗАГОЛОВОК]\n"
        "короткий заголовок события (до 80 символов)\n\n"
        "[ЧТО ПРОИЗОШЛО]\n"
        "конкретные факты: кто, что, когда, версия/цифры если есть (2-3 предложения)\n\n"
        "[ПОЧЕМУ ВАЖНО]\n"
        "практический эффект для coding agents / AI workflows / MCP экосистемы\n\n"
        "[ЗОНА ВЛИЯНИЯ]\n"
        f"выбери из: {_AI_AGENTS_AFFECTED_AREAS}\n"
        "перечисли через запятую, только подходящие\n\n"
        "[ДОСТОВЕРНОСТЬ]\n"
        "verified | partially_verified | signal_only\n"
    )


def _parse_ai_agents_response(text: str) -> dict:
    """Parse structured LLM response for ai_agents category."""
    import re as _re
    any_tag = r"\[(?:ЗАГОЛОВОК|ЧТО ПРОИЗОШЛО|ПОЧЕМУ ВАЖНО|ЗОНА ВЛИЯНИЯ|ДОСТОВЕРНОСТЬ)\]"

    def _extract(tag: str) -> str:
        pat = _re.compile(
            r"\[" + _re.escape(tag) + r"\]\s*(.*?)(?=" + any_tag + r"|$)",
            _re.DOTALL | _re.IGNORECASE,
        )
        m = pat.search(text)
        if not m:
            return ""
        return _re.sub(r"^\([^)]{3,120}\)\s*", "", m.group(1).strip(), flags=_re.DOTALL).strip()

    tag_pos = text.find("[ЗАГОЛОВОК]")
    if tag_pos > 0:
        text = text[tag_pos:]

    # Normalize confidence value
    raw_conf = _extract("ДОСТОВЕРНОСТЬ").lower()
    if "verified" in raw_conf and "partial" not in raw_conf:
        confidence = "verified"
    elif "partial" in raw_conf:
        confidence = "partially_verified"
    else:
        confidence = "signal_only"

    return {
        "title":          _extract("ЗАГОЛОВОК"),
        "summary_ru":     _extract("ЧТО ПРОИЗОШЛО"),
        "why_it_matters": _extract("ПОЧЕМУ ВАЖНО"),
        "editor_take":    "",
        "affected_area":  _extract("ЗОНА ВЛИЯНИЯ"),
        "confidence":     confidence,
    }


def build_event_prompt(event: DigestEvent, memory_context: str = "", user_profile: str = "") -> str:
    """Build synthesis prompt for a single DigestEvent.

    Includes up to _MAX_TITLES unique titles and _MAX_SNIPPETS snippets.
    Optionally injects a memory_context block before the instruction section.

    Prompt goals:
      - No retelling: "не пересказывай"
      - Explain significance: "объясни почему важно"
      - Flag continuations: "если это продолжение — скажи"
      - Flag weak signals: "если нет новой информации — назови слабым сигналом"
      - Remove noise: "убирай рекламный язык"
    """
    # Collect unique titles
    titles_seen: set = set()
    titles: List[str] = []
    for a in event.articles:
        t = (a.title or "").strip()
        if t and t.lower() not in titles_seen:
            titles_seen.add(t.lower())
            titles.append(t)
        if len(titles) >= _MAX_TITLES:
            break

    # Collect non-empty snippets
    snippets: List[str] = []
    for a in event.articles:
        s = (a.snippet or "").strip()
        if s and len(snippets) < _MAX_SNIPPETS:
            snippets.append(s[:_SNIPPET_CHARS])

    titles_block = "\n".join(f"- {t}" for t in titles)
    snippets_block = (
        "\n".join(f"- {s}" for s in snippets)
        if snippets else "(фрагменты источников недоступны)"
    )
    memory_block = (
        f"\n{memory_context}\n"
        if memory_context else ""
    )

    return (
        "Ты опытный новостной редактор. Пишешь аналитическую карточку для конкретного читателя.\n\n"
        "СОБЫТИЕ:\n"
        f"Заголовки:\n{titles_block}\n\n"
        f"Фрагменты источников:\n{snippets_block}\n"
        f"{memory_block}\n"
        f"ПРОФИЛЬ ЧИТАТЕЛЯ:\n{user_profile if user_profile else _DEFAULT_USER_PROFILE}\n\n"
        "ИНСТРУКЦИИ:\n"
        "1. [ЗАГОЛОВОК]: суммируй данные источников и напиши понятный, говорящий заголовок. "
           "Не придумывай и не перевирай — только то, что прямо следует из источников. До 80 символов.\n"
        "2. [СУТЬ]: изложи факты — не затравку, а полноценную суть новости. "
           "Небольшой абзац (2–4 предложения). Пиши конкретно: кто, что, когда, сколько. "
           "Не придумывай детали, не перевирай, суммируй то, что есть в источниках.\n"
        "3. [ПОЧЕМУ ВАЖНО]: объясни почему эта новость важна именно для этого читателя и его интересов. "
           "Не общие слова — конкретная связь с его жизнью, работой или интересами.\n"
        "4. [РЕДАКЦИОННЫЙ КОММЕНТАРИЙ]: субъективная оценка, неочевидный угол или скептицизм. "
           "Можно одно предложение.\n"
        "5. Если новость — продолжение известной темы, укажи это в [СУТЬ].\n"
        "6. Если новость не несёт новой информации — напиши об этом в [РЕДАКЦИОННЫЙ КОММЕНТАРИЙ].\n"
        '7. Убирай рекламный язык: "революционный", "потрясающий", "прорывной".\n'
        "8. Только русский язык.\n\n"
        "ФОРМАТ ОТВЕТА — строго только эти четыре тега, без дополнительного текста:\n\n"
        "[ЗАГОЛОВОК]\n"
        "заголовок\n\n"
        "[СУТЬ]\n"
        "факты и суть события\n\n"
        "[ПОЧЕМУ ВАЖНО]\n"
        "почему важно именно для тебя\n\n"
        "[РЕДАКЦИОННЫЙ КОММЕНТАРИЙ]\n"
        "субъективная оценка"
    )


# ---------------------------------------------------------------------------
# Single-event synthesis
# ---------------------------------------------------------------------------

def synthesize_event(event: DigestEvent, user_id: Optional[str] = None, user_profile: str = "", config: Any = None) -> SynthesizedItem:  # type: ignore[valid-type]
    """Synthesize one DigestEvent → SynthesizedItem.

    1. Fetch memory context (if user_id given).
    2. Build prompt.
    3. Call LLM.
    4. Parse response (lenient).
    5. Fill gaps for partial parse.
    6. Return SynthesizedItem; fall back on any unrecoverable error.
    """
    memory_ctx = _fetch_memory_context(user_id, event.canonical_title) if user_id else ""

    # Custom prompt override from config.prompts["synthesis"] — opt-in
    custom = None
    if config is not None:
        prompts = getattr(config, "prompts", None)
        if isinstance(prompts, dict):
            custom = prompts.get("synthesis")

    if custom:
        try:
            titles = "\n".join(
                f"- {(a.title or '').strip()}" for a in event.articles if getattr(a, "title", "")
            )
            snippets = "\n".join(
                f"- {(a.snippet or '').strip()[:250]}" for a in event.articles if getattr(a, "snippet", "")
            )
            prompt = custom.format(
                titles=titles,
                snippets=snippets,
                memory_context=memory_ctx,
                user_profile=user_profile or _DEFAULT_USER_PROFILE,
                canonical_title=event.canonical_title,
            )
        except Exception as e:
            logger.warning("[synthesizer] custom prompt failed, using default: %s", e)
            custom = None

    if not custom:
        if event.category == "ai_agents":
            prompt = build_ai_agents_event_prompt(event, memory_context=memory_ctx, user_profile=user_profile)
        else:
            prompt = build_event_prompt(event, memory_context=memory_ctx, user_profile=user_profile)
    short_name = event.canonical_title[:55]

    try:
        # Use LLMRouter if config provided (newsbrief mode); fallback to legacy AI_WORKER_URL
        raw = ""
        if config is not None:
            try:
                from newsbrief.llm.router import LLMRouter
                router = LLMRouter(config)
                r = router.generate(prompt, task="synthesis", max_tokens=600)
                raw = (r.text or "").strip()
            except Exception as _re:
                logger.warning("[synthesizer] LLMRouter failed, fallback to AI_WORKER: %s", _re)
        if not raw:
            with httpx.Client(timeout=AI_WORKER_TIMEOUT) as client:
                resp = client.post(
                    f"{AI_WORKER_URL}/llm/generate",
                    json={"prompt": prompt, "model": DIGEST_LLM_MODEL},
                )
                resp.raise_for_status()
                raw = resp.json().get("response", "").strip()
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()

        if not raw:
            logger.warning("[synthesizer] empty response event=%r", short_name)
            return _build_fallback(event)

        if event.category == "ai_agents":
            parsed = _parse_ai_agents_response(raw)
            parsed["_partial"] = not parsed.get("title") or not parsed.get("summary_ru")
        else:
            parsed = _parse_llm_response(raw)

        if parsed is None:
            logger.warning("[synthesizer] full fallback (nothing parsed) event=%r raw[:80]=%r",
                           short_name, raw[:80])
            return _build_fallback(event)

        partial = parsed.pop("_partial", False)
        if partial:
            logger.warning("[synthesizer] partial parse event=%r title=%r summary=%r",
                           short_name, bool(parsed["title"]), bool(parsed["summary_ru"]))

        # Fill gaps for partial parse
        if not parsed["title"]:
            parsed["title"] = event.canonical_title
        if not parsed["summary_ru"]:
            fb = _build_fallback(event)
            parsed["summary_ru"] = fb.summary_ru

        logger.info("[synthesizer] ok%s event=%r title=%r mem=%s",
                    " (partial)" if partial else "",
                    short_name, parsed["title"][:50], "yes" if memory_ctx else "no")

        return SynthesizedItem(
            category=       event.category,
            title=          parsed["title"],
            summary_ru=     parsed["summary_ru"],
            why_it_matters= parsed["why_it_matters"],
            editor_take=    parsed["editor_take"],
            sources=        event.sources,
            published_at=   event.published_at.isoformat() if event.published_at else None,
            llm_used=       True,
            affected_area=   parsed.get("affected_area", ""),
            confidence=      parsed.get("confidence", event.role if hasattr(event, "role") else ""),
            global_importance_score=  getattr(event, "global_importance_score", 0.0),
            personal_relevance_score= getattr(event, "personal_relevance_score", 0.0),
            final_score=              getattr(event, "final_score", 0.0),
        )

    except httpx.TimeoutException:
        logger.warning("[synthesizer] LLM timeout event=%r", short_name)
    except httpx.ConnectError:
        logger.warning("[synthesizer] LLM unreachable event=%r", short_name)
    except Exception as e:
        logger.error("[synthesizer] error event=%r: %s", short_name, e)

    return _build_fallback(event)


# ---------------------------------------------------------------------------
# Category-level synthesis
# ---------------------------------------------------------------------------

def synthesize_category_digest(
    events: List[DigestEvent],
    max_events: int = 5,
    user_id: Optional[str] = None,
    user_profile: str = "",
) -> List[SynthesizedItem]:
    """Synthesize up to max_events DigestEvents for one category.

    Selection priority:
      1. Multi-article events first (more evidence).
      2. Among equal article counts: events with non-empty snippets first.

    Parallel: DIGEST_PARALLEL_WORKERS simultaneous LLM calls (default 2).
    Result order matches selection order (not completion order).
    One thread failure does not abort others.
    """
    if not events:
        return []

    def _priority(e: DigestEvent) -> tuple:
        # Use ranked score if set by ranker.rank_events_for_user()
        fs = getattr(e, "final_score", 0.0)
        if fs > 0.0:
            return (-fs,)
        has_snippets = any((a.snippet or "").strip() for a in e.articles)
        return (-len(e.articles), 0 if has_snippets else 1)

    selected: List[DigestEvent] = sorted(events, key=_priority)[:max_events]

    # results_map preserves insertion order via dict (Python 3.7+)
    results_map: Dict[int, SynthesizedItem] = {}

    with ThreadPoolExecutor(max_workers=DIGEST_PARALLEL_WORKERS) as pool:
        future_to_idx = {
            pool.submit(synthesize_event, ev, user_id, user_profile): i
            for i, ev in enumerate(selected)
        }
        for fut in as_completed(future_to_idx):
            idx = future_to_idx[fut]
            ev  = selected[idx]
            try:
                results_map[idx] = fut.result()
            except Exception as e:
                logger.error("[synthesizer] thread error event=%r: %s",
                             ev.canonical_title[:50], e)
                results_map[idx] = _build_fallback(ev)

    results = [results_map[i] for i in range(len(selected))]

    llm_count = sum(1 for r in results if r.llm_used)
    logger.info(
        "[synthesizer] done cat=%s events=%d llm=%d fallback=%d workers=%d",
        selected[0].category, len(results), llm_count,
        len(results) - llm_count, DIGEST_PARALLEL_WORKERS,
    )
    return results
