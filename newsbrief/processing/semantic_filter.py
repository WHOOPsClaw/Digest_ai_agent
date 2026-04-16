"""processing/semantic_filter.py — LLM-based pre-filter before synthesis.

Batches up to 10 event titles per LLM call, asks the model to return a JSON
object of the form:

    {"keep_indices": [0, 2, 5], "reasons": {"1": "excluded: sports", ...}}

Fails open on any error (keeps all events in the batch) so a flaky LLM can
never silently drop real news.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger("newsbrief")

BATCH_SIZE = 10


def _event_title(ev: Any) -> str:
    t = getattr(ev, "canonical_title", None) or getattr(ev, "title", None) or ""
    return str(t).strip()


def build_filter_prompt(
    items: list[dict],
    include_criteria: list[str],
    exclude_criteria: list[str],
) -> str:
    """Build an LLM prompt asking for a JSON keep/drop decision per item."""
    lines = ["You are a semantic news filter. You are given numbered headlines."]
    if include_criteria:
        lines.append("KEEP items that match ANY of these criteria:")
        for c in include_criteria:
            lines.append(f"  - {c}")
    if exclude_criteria:
        lines.append("EXCLUDE items that match ANY of these criteria:")
        for c in exclude_criteria:
            lines.append(f"  - {c}")
    lines.append("")
    lines.append("Headlines:")
    for i, item in enumerate(items):
        title = item.get("title", "") if isinstance(item, dict) else str(item)
        lines.append(f"{i}. {title}")
    lines.append("")
    lines.append(
        'Respond with ONLY a compact JSON object:\n'
        '{"keep_indices": [<int>, ...], "reasons": {"<int>": "<short reason>"}}'
    )
    lines.append("Do not wrap in Markdown. Do not add commentary.")
    return "\n".join(lines)


def _parse_response(text: str, batch_len: int) -> set[int]:
    """Extract keep_indices from an LLM response. Fail-open: on parse error keep all."""
    if not text:
        return set(range(batch_len))
    # Strip common wrappers (```json ... ```)
    cleaned = text.strip()
    m = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not m:
        logger.warning("[semantic_filter] no JSON in LLM response — failing open")
        return set(range(batch_len))
    try:
        data = json.loads(m.group(0))
    except Exception as e:
        logger.warning("[semantic_filter] JSON parse failed (%s) — failing open", e)
        return set(range(batch_len))

    idx_raw = data.get("keep_indices")
    if not isinstance(idx_raw, list):
        logger.warning("[semantic_filter] missing keep_indices — failing open")
        return set(range(batch_len))
    out: set[int] = set()
    for x in idx_raw:
        try:
            i = int(x)
        except Exception:
            continue
        if 0 <= i < batch_len:
            out.add(i)
    return out


def filter_events_semantically(
    events: list,
    include: list[str],
    exclude: list[str],
    llm_router: Any,
) -> list:
    """Batch-filter events via LLM.

    Returns kept events (same object references, order preserved).
    On any per-batch LLM error: fail open for that batch (keep all).
    If no criteria set, returns events unchanged.
    """
    if not events:
        return events
    if not (include or exclude):
        return events
    if llm_router is None:
        return events

    kept: list = []
    total_tokens_in  = 0
    total_tokens_out = 0

    for start in range(0, len(events), BATCH_SIZE):
        batch = events[start : start + BATCH_SIZE]
        items = [{"title": _event_title(ev)} for ev in batch]
        prompt = build_filter_prompt(items, include, exclude)
        try:
            resp = llm_router.generate(prompt, task="filter")
        except Exception as e:
            logger.warning("[semantic_filter] LLM call failed (%s) — keeping batch", e)
            kept.extend(batch)
            continue

        # Track tokens if available
        for attr in ("tokens_in", "prompt_tokens", "input_tokens"):
            if hasattr(resp, attr):
                total_tokens_in += getattr(resp, attr) or 0
                break
        for attr in ("tokens_out", "completion_tokens", "output_tokens"):
            if hasattr(resp, attr):
                total_tokens_out += getattr(resp, attr) or 0
                break

        text = getattr(resp, "text", None) or getattr(resp, "content", None) or str(resp)
        keep_idx = _parse_response(text, len(batch))
        for i, ev in enumerate(batch):
            if i in keep_idx:
                kept.append(ev)

    logger.info(
        "[semantic_filter] kept %d/%d events (tokens in=%d out=%d)",
        len(kept), len(events), total_tokens_in, total_tokens_out,
    )
    return kept


# ---------------------------------------------------------------------------
# Article-level batch filter (spec API)
# ---------------------------------------------------------------------------

_SNIPPET_CHARS = 180


def _articles_to_json(batch: list) -> str:
    out = []
    for i, a in enumerate(batch):
        title = (getattr(a, "title", "") or "")[:200]
        snippet = (getattr(a, "snippet", "") or "")[:_SNIPPET_CHARS]
        out.append({"idx": i, "title": title, "snippet_short": snippet})
    return json.dumps(out, ensure_ascii=False)


def _build_article_prompt(
    batch: list,
    include_patterns: list,
    exclude_patterns: list,
    user_profile: str = "",
    custom_prompt: str = "",
) -> str:
    articles_json = _articles_to_json(batch)
    includes = ", ".join(include_patterns) if include_patterns else (user_profile or "общие интересы")
    excludes = ", ".join(exclude_patterns) if exclude_patterns else "нет"

    if custom_prompt:
        try:
            return custom_prompt.format(
                includes=includes, excludes=excludes,
                articles_json=articles_json, user_profile=user_profile or "",
            )
        except Exception:
            pass

    return (
        "Ты фильтруешь новости для персонального дайджеста.\n\n"
        f"Пользователь любит: {includes}\n"
        f"Пользователь НЕ любит: {excludes}\n\n"
        f"Заголовки (JSON):\n{articles_json}\n\n"
        'Для каждой: keep (true/false). Верни JSON: {"keep": [0, 2, 5, ...]}.\n'
        "Оставь только те, которые совпадают с \"любит\" И не совпадают с \"не любит\"."
    )


def _parse_keep_indices(text: str, batch_size: int) -> list[int]:
    if not text:
        return list(range(batch_size))
    m = re.search(r"\{[^{}]*\"keep\"[^{}]*\}", text, re.DOTALL)
    payload = m.group(0) if m else text
    try:
        data = json.loads(payload)
        keep = data.get("keep", [])
        return [int(i) for i in keep
                if isinstance(i, (int, float)) and 0 <= int(i) < batch_size]
    except Exception:
        m2 = re.search(r"\[([\d,\s]+)\]", text)
        if m2:
            try:
                return [int(x) for x in m2.group(1).split(",")
                        if x.strip().isdigit() and 0 <= int(x) < batch_size]
            except Exception:
                pass
    logger.warning("[semantic_filter] could not parse LLM response: %r", text[:120])
    return list(range(batch_size))


def filter_batch(
    articles: list,
    config: Any,
    llm_router: Any,
    include_patterns: list = None,
    exclude_patterns: list = None,
) -> list:
    """Batch-filter RawArticle-like objects with an LLM (fail-open).

    Returns only the articles the model decided to keep.
    """
    if not articles:
        return []
    if llm_router is None:
        return list(articles)

    filters_cfg = getattr(config, "filters", None)
    if include_patterns is None and filters_cfg is not None:
        include_patterns = list(getattr(filters_cfg, "semantic_include", []) or [])
    if exclude_patterns is None and filters_cfg is not None:
        exclude_patterns = list(getattr(filters_cfg, "semantic_exclude", []) or [])
    include_patterns = include_patterns or []
    exclude_patterns = exclude_patterns or []

    user_profile = getattr(getattr(config, "user", None), "profile", "") or ""
    custom_prompt = ""
    prompts = getattr(config, "prompts", None)
    if isinstance(prompts, dict):
        custom_prompt = prompts.get("filter", "") or ""

    kept: list = []
    for start in range(0, len(articles), BATCH_SIZE):
        batch = articles[start:start + BATCH_SIZE]
        prompt = _build_article_prompt(
            batch, include_patterns, exclude_patterns, user_profile, custom_prompt,
        )
        try:
            resp = llm_router.generate(prompt, task="filter")
            text = getattr(resp, "text", None) or getattr(resp, "content", None) or str(resp)
            keep_idx = _parse_keep_indices(text, len(batch))
        except Exception as e:
            logger.warning("[semantic_filter] LLM failed on batch %d: %s — keeping all",
                           start // BATCH_SIZE, e)
            keep_idx = list(range(len(batch)))

        for i in keep_idx:
            kept.append(batch[i])

    logger.info("[semantic_filter] filter_batch kept %d / %d articles",
                len(kept), len(articles))
    return kept
