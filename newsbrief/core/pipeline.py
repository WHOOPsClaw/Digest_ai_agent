"""core/pipeline.py — main pipeline orchestrator.

fetch → filter → dedup → group → rank → synthesize → compose → deliver.

Records timing in `pipeline_runs` table for adaptive scheduler buffer.
Degrades gracefully if sprint 2 (sources) / sprint 3 (llm) aren't ready.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import date as _date
from datetime import datetime
from typing import Optional

logger = logging.getLogger("newsbrief")

# --- Optional sprint 2/3 modules (graceful fallback) -----------------------
try:
    from newsbrief.sources import fetch_all  # sprint 2 interface (may not exist yet)
except Exception:  # noqa: BLE001
    fetch_all = None  # type: ignore[assignment]

try:
    _legacy_collect = None  # legacy fetcher removed
except Exception:  # noqa: BLE001
    _legacy_collect = None  # type: ignore[assignment]


def _insert_pipeline_run(storage, started_at: datetime, provider: str) -> Optional[int]:
    if storage is None:
        return None
    try:
        storage.execute(
            "INSERT INTO pipeline_runs (run_date, started_at, llm_provider, status) "
            "VALUES (%s, %s, %s, %s)",
            (started_at.date().isoformat(), started_at.isoformat(), provider, "running"),
        )
        row = storage.fetchone(
            "SELECT id FROM pipeline_runs ORDER BY id DESC LIMIT 1"
        )
        return int(row["id"]) if row else None
    except Exception as e:
        logger.warning("[pipeline] pipeline_runs insert failed: %s", e)
        return None


def _finalize_run(
    storage,
    run_id: Optional[int],
    started_at: datetime,
    status: str,
    item_count: int = 0,
    fetch_sec: float = 0.0,
    synth_sec: float = 0.0,
    error: str = "",
) -> None:
    if storage is None or run_id is None:
        return
    finished = datetime.utcnow()
    duration = (finished - started_at).total_seconds()
    try:
        storage.execute(
            "UPDATE pipeline_runs SET finished_at=%s, duration_sec=%s, "
            "fetch_sec=%s, synthesize_sec=%s, item_count=%s, status=%s, error=%s "
            "WHERE id=%s",
            (
                finished.isoformat(),
                duration,
                fetch_sec,
                synth_sec,
                item_count,
                status,
                error[:500] if error else "",
                run_id,
            ),
        )
    except Exception as e:
        logger.warning("[pipeline] pipeline_runs update failed: %s", e)


def _save_digest(
    storage,
    today: _date,
    item_count: int,
    full_text: str,
    parts_count: int,
    metadata: dict,
) -> Optional[int]:
    if storage is None:
        return None
    try:
        storage.execute(
            "INSERT INTO digests (digest_date, item_count, full_text, parts_count, "
            "metadata_json, sent_at) VALUES (%s, %s, %s, %s, %s, %s)",
            (
                today.isoformat(),
                item_count,
                full_text,
                parts_count,
                json.dumps(metadata, ensure_ascii=False),
                datetime.utcnow().isoformat(),
            ),
        )
        row = storage.fetchone("SELECT id FROM digests ORDER BY id DESC LIMIT 1")
        return int(row["id"]) if row else None
    except Exception as e:
        logger.warning("[pipeline] digest insert failed: %s", e)
        return None


def run_pipeline(
    config,
    storage=None,
    llm_router=None,
    send: bool = True,
) -> dict:
    """Run full pipeline. Returns a result dict.

    Keys: success, item_count, parts, duration_sec, digest_id, error (if fail).
    """
    started_at = datetime.utcnow()
    t0 = time.monotonic()
    provider = (config.llm.preset or "unknown") if config else "unknown"
    run_id = _insert_pipeline_run(storage, started_at, provider)

    result: dict = {
        "success":      False,
        "item_count":   0,
        "parts":        0,
        "duration_sec": 0.0,
        "digest_id":    None,
    }

    # --- 0. Progress notification (best-effort) ---
    if send:
        try:
            from newsbrief.delivery.telegram import TelegramChannel
            _progress = TelegramChannel.from_config(config)
            _progress.send([
                "🔄 Собираю дайджест...\nЭто может занять 3-5 минут."
            ])
        except Exception as e:
            logger.warning("[pipeline] progress notify failed: %s", e)

    # Apply serial-mode override for synthesizer workers.
    try:
        if getattr(getattr(config, "llm", None), "serial", False):
            import os as _os
            _os.environ["DIGEST_PARALLEL_WORKERS"] = "1"
            import newsbrief.processing.synthesizer as _synth
            _synth.DIGEST_PARALLEL_WORKERS = 1
    except Exception:
        pass

    try:
        # --- 1. Fetch ---
        categories = [t.id for t in (config.topics or [])] or [
            "world", "russia_moscow", "ai", "tech", "games", "ai_agents",
        ]
        fetch_start = time.monotonic()
        articles_by_cat: dict = {}
        if fetch_all is not None:
            try:
                articles_by_cat = fetch_all(config)  # type: ignore[misc]
            except Exception as e:
                logger.warning("[pipeline] new fetch_all failed, falling back: %s", e)
                articles_by_cat = {}
        if not articles_by_cat and _legacy_collect is not None:
            articles_by_cat = _legacy_collect(categories)
        fetch_sec = time.monotonic() - fetch_start
        logger.info(
            "[pipeline] fetched: cats=%d total_articles=%d",
            len(articles_by_cat),
            sum(len(v) for v in articles_by_cat.values()),
        )

        # --- 1b. Semantic pre-filter (LLM-based, before dedup) ---
        try:
            filters_cfg = getattr(config, "filters", None)
            if (filters_cfg is not None
                    and getattr(filters_cfg, "enabled", False)
                    and (getattr(filters_cfg, "semantic_include", None)
                         or getattr(filters_cfg, "semantic_exclude", None))
                    and llm_router is not None):
                from newsbrief.processing.semantic_filter import filter_batch
                for cat, arts in list(articles_by_cat.items()):
                    if arts:
                        articles_by_cat[cat] = filter_batch(
                            arts, config, llm_router,
                            list(filters_cfg.semantic_include or []),
                            list(filters_cfg.semantic_exclude or []),
                        )
        except Exception as e:
            logger.warning("[pipeline] semantic filter failed, skipping: %s", e)

        # --- 2. Filter / Dedup / Group / Rank per category ---
        from newsbrief.processing.filter import event_matches_blacklist
        from newsbrief.processing.dedup import deduplicate_against_batch
        from newsbrief.processing.events import group_similar_articles
        from newsbrief.processing.ranker import rank_events_for_user

        blacklist = []
        for topic in (config.topics or []):
            blacklist.extend(topic.blacklist or [])

        # Precompute source boosts from feedback (neutral if disabled / no data)
        source_boosts: dict = {}
        try:
            if getattr(getattr(config, "learning", None), "enabled", False):
                from newsbrief.feedback.learner import compute_source_boosts
                source_boosts = compute_source_boosts(
                    storage, config,
                    min_feedback=getattr(config.learning, "min_feedback", 10),
                )
        except Exception as e:
            logger.warning("[pipeline] compute_source_boosts failed: %s", e)

        # Semantic filter criteria
        sem_include = list(getattr(getattr(config, "filters", None), "semantic_include", []) or [])
        sem_exclude = list(getattr(getattr(config, "filters", None), "semantic_exclude", []) or [])

        events_by_cat: dict = {}
        for cat, articles in articles_by_cat.items():
            if not articles:
                continue
            deduped = deduplicate_against_batch(articles)
            events  = group_similar_articles(deduped)
            events  = [e for e in events if not event_matches_blacklist(e, blacklist)]

            # --- Phase 6: smart entity grouping + cross-digest dedup ---
            dedup_cfg = getattr(config, "dedup", None)
            if dedup_cfg is not None and events:
                try:
                    from newsbrief.processing.semantic_dedup import (
                        group_by_entities, filter_recent_duplicates,
                    )
                    entity_router = llm_router if getattr(dedup_cfg, "use_llm_entities", False) else None
                    if getattr(dedup_cfg, "entity_grouping", True):
                        events = group_by_entities(
                            events,
                            threshold=float(getattr(dedup_cfg, "entity_threshold", 0.5)),
                            llm_router=entity_router,
                        )
                    events = filter_recent_duplicates(
                        events,
                        storage,
                        days=int(getattr(dedup_cfg, "cross_digest_days", 7)),
                        threshold=float(getattr(dedup_cfg, "semantic_similarity_threshold", 0.7)),
                        llm_router=entity_router,
                    )
                    # Drop events whose matched story was in a very recent digest.
                    try:
                        from newsbrief.core.stories import (
                            ensure_stories_table, find_matching_story,
                            was_in_recent_digest,
                        )
                        ensure_stories_table(storage)
                        recent_days = int(getattr(dedup_cfg, "recent_story_days", 3))
                        filtered = []
                        for ev in events:
                            ents = getattr(ev, "entities", None) or {}
                            sid = find_matching_story(ents, storage, days=14)
                            if sid and was_in_recent_digest(sid, recent_days, storage):
                                logger.info(
                                    "[pipeline] drop event — story %d seen in last %d days",
                                    sid, recent_days,
                                )
                                continue
                            filtered.append(ev)
                        events = filtered
                    except Exception as e:
                        logger.warning("[pipeline] stories filter failed: %s", e)
                except Exception as e:
                    logger.warning("[pipeline] semantic_dedup failed: %s", e)

            # Optional semantic pre-filter via LLM
            if (sem_include or sem_exclude) and llm_router is not None and events:
                from newsbrief.processing.semantic_filter import filter_events_semantically
                before = len(events)
                try:
                    events = filter_events_semantically(
                        events, sem_include, sem_exclude, llm_router,
                    )
                except Exception as e:
                    logger.warning("[pipeline] semantic_filter failed (%s) — keeping all", e)
                logger.info(
                    "[pipeline] semantic_filter %s: %d → %d",
                    cat, before, len(events),
                )

            try:
                ranked = rank_events_for_user(events, category=cat)
            except TypeError:
                ranked = rank_events_for_user(events, cat)  # type: ignore[misc]

            # Apply learned source boosts to final_score
            if source_boosts:
                import re as _re
                def _src_key(raw: str) -> str:
                    return _re.sub(r"^(rss:|tg:|search:?)\s*", "", (raw or "").lower()).strip()
                for ev in ranked:
                    srcs = {_src_key(getattr(a, "source", "")) for a in getattr(ev, "articles", [])}
                    if not srcs:
                        continue
                    factors = [source_boosts[s] for s in srcs if s in source_boosts]
                    if not factors:
                        continue
                    factor = sum(factors) / len(factors)
                    cur = getattr(ev, "final_score", 0.0) or 0.0
                    try:
                        setattr(ev, "final_score", round(cur * factor, 4))
                    except Exception:
                        pass
                ranked = sorted(ranked, key=lambda e: getattr(e, "final_score", 0.0), reverse=True)

            events_by_cat[cat] = ranked

        # --- 3. Synthesize ---
        synth_start = time.monotonic()
        from newsbrief.processing.synthesizer import synthesize_event

        items_by_cat: dict = {}
        for cat, events in events_by_cat.items():
            synthesized = []
            for ev in events[:10]:
                try:
                    item = synthesize_event(ev, config=config)
                    synthesized.append(item)
                except Exception as e:
                    logger.warning("[pipeline] synthesize failed (%s): %s", cat, e)
            items_by_cat[cat] = synthesized
        synth_sec = time.monotonic() - synth_start

        # --- 4. Compose ---
        from newsbrief.processing.composer import compose_digest_issue
        today = _date.today()
        card_style = getattr(getattr(config, "format", None), "card_style", None)
        issue = compose_digest_issue(items_by_cat, issue_date=today, card_style=card_style)

        # --- 5. Persist digest ---
        digest_id = _save_digest(
            storage, today, issue.item_count,
            issue.full_text, len(issue.telegram_parts), issue.metadata,
        )
        result["digest_id"]  = digest_id
        # --- Phase 6: update stories table ---
        try:
            from newsbrief.core.stories import (
                ensure_stories_table, find_matching_story,
                create_story, update_story,
            )
            from newsbrief.processing.semantic_dedup import extract_entities
            ensure_stories_table(storage)
            for cat_events in events_by_cat.values():
                for ev in cat_events[:10]:
                    title = getattr(ev, "canonical_title", "") or ""
                    ents  = getattr(ev, "entities", None)
                    if not ents:
                        ents = extract_entities(title)
                    sid = find_matching_story(ents, storage, days=14)
                    if sid:
                        update_story(sid, digest_id, storage)
                    else:
                        create_story(title, ents, digest_id, storage)
        except Exception as e:
            logger.warning("[pipeline] stories upsert failed: %s", e)

        result["item_count"] = issue.item_count
        result["parts"]      = len(issue.telegram_parts)
        result["full_text"]  = issue.full_text
        result["telegram_parts"] = issue.telegram_parts

        # --- 6. Deliver ---
        if send:
            from newsbrief.delivery.telegram import TelegramChannel
            channel = TelegramChannel.from_config(config)
            dres = channel.send_digest(
                issue.telegram_parts,
                digest_id=digest_id or 0,
            )
            result["delivery"] = {
                "ok":          dres.ok,
                "sent_parts":  dres.sent_parts,
                "total_parts": dres.total_parts,
                "skipped":     dres.skipped,
                "errors":      dres.errors,
            }
            if not dres.ok and not dres.skipped:
                logger.error("[pipeline] delivery failed: %s", dres.errors)

        duration = time.monotonic() - t0
        result["duration_sec"] = duration
        result["success"]      = True

        _finalize_run(
            storage, run_id, started_at, "ok",
            item_count=issue.item_count,
            fetch_sec=fetch_sec, synth_sec=synth_sec,
        )
        logger.info(
            "[pipeline] done: items=%d parts=%d duration=%.1fs",
            issue.item_count, len(issue.telegram_parts), duration,
        )
        return result

    except Exception as e:
        logger.exception("[pipeline] FAILED")
        duration = time.monotonic() - t0
        result["duration_sec"] = duration
        result["error"]        = str(e)
        _finalize_run(storage, run_id, started_at, "error", error=str(e))
        if send:
            try:
                from newsbrief.delivery.telegram import TelegramChannel
                TelegramChannel.from_config(config).send([
                    "⚠️ Ошибка при сборке. Проверь логи."
                ])
            except Exception as _err:
                logger.warning("[pipeline] failure-notify failed: %s", _err)
        return result
