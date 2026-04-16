"""core/stories.py — persistent story tracking across digests.

A "story" = a long-running real-world topic (e.g. "Tesla Cybertruck recall"),
distinct from a single digest card. Stories let us suppress repeat coverage
across consecutive digests.

Schema:
    stories(
        id                INTEGER PK,
        canonical_title   TEXT,
        entities_json     TEXT,
        first_seen_at     TIMESTAMP,
        last_seen_at      TIMESTAMP,
        card_count        INTEGER,
        digest_ids_json   TEXT   -- JSON array of digest ids
    )
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from newsbrief.processing.semantic_dedup import entity_overlap

logger = logging.getLogger("newsbrief")


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def ensure_stories_table(storage: Any) -> None:
    """Create `stories` table if it does not exist. Fails open on any error."""
    if storage is None:
        return
    try:
        storage.execute(
            """CREATE TABLE IF NOT EXISTS stories (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                canonical_title  TEXT NOT NULL,
                entities_json    TEXT,
                first_seen_at    TIMESTAMP,
                last_seen_at     TIMESTAMP,
                card_count       INTEGER DEFAULT 1,
                digest_ids_json  TEXT
            )"""
        )
        storage.execute(
            "CREATE INDEX IF NOT EXISTS idx_stories_last_seen "
            "ON stories(last_seen_at DESC)"
        )
    except Exception as e:
        logger.warning("[stories] ensure_stories_table failed: %s", e)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row_get(row: Any, key: str, default: Any = None) -> Any:
    if row is None:
        return default
    if isinstance(row, dict):
        return row.get(key, default)
    try:
        return row[key]
    except Exception:
        return default


def _parse_json(s: Any, default: Any) -> Any:
    if not s:
        return default
    if isinstance(s, (dict, list)):
        return s
    try:
        return json.loads(s)
    except Exception:
        return default


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def find_matching_story(
    entities: Dict[str, List[str]],
    storage: Any,
    days: int = 14,
    threshold: float = 0.5,
) -> Optional[int]:
    """Find a story with overlapping entities seen in last N days.

    Returns the best-matching story id or None.
    """
    if storage is None or not entities:
        return None
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
    try:
        rows = storage.fetchall(
            "SELECT id, entities_json FROM stories WHERE last_seen_at >= %s",
            (cutoff,),
        )
    except Exception as e:
        logger.debug("[stories] find_matching_story query failed: %s", e)
        return None

    best_id:    Optional[int] = None
    best_score: float = 0.0
    for r in rows or []:
        sid   = _row_get(r, "id")
        ejson = _row_get(r, "entities_json")
        other = _parse_json(ejson, {})
        score = entity_overlap(entities, other)
        if score >= threshold and score > best_score:
            best_id, best_score = int(sid), score
    return best_id


def create_story(
    canonical_title: str,
    entities: Dict[str, List[str]],
    digest_id: Optional[int],
    storage: Any,
) -> Optional[int]:
    """Insert a new story row. Returns new id, or None on failure."""
    if storage is None:
        return None
    now = datetime.utcnow().isoformat()
    digest_ids = json.dumps([digest_id] if digest_id else [])
    ent_json   = json.dumps(entities or {}, ensure_ascii=False)
    try:
        storage.execute(
            "INSERT INTO stories "
            "(canonical_title, entities_json, first_seen_at, last_seen_at, "
            " card_count, digest_ids_json) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (canonical_title or "", ent_json, now, now, 1, digest_ids),
        )
        row = storage.fetchone("SELECT id FROM stories ORDER BY id DESC LIMIT 1")
        return int(_row_get(row, "id")) if row else None
    except Exception as e:
        logger.warning("[stories] create_story failed: %s", e)
        return None


def update_story(story_id: int, digest_id: Optional[int], storage: Any) -> None:
    """Append digest_id, bump last_seen_at and card_count."""
    if storage is None or not story_id:
        return
    try:
        row = storage.fetchone(
            "SELECT digest_ids_json, card_count FROM stories WHERE id = %s",
            (story_id,),
        )
        if not row:
            return
        digest_ids = _parse_json(_row_get(row, "digest_ids_json"), [])
        if digest_id and digest_id not in digest_ids:
            digest_ids.append(digest_id)
        card_count = int(_row_get(row, "card_count") or 0) + 1
        storage.execute(
            "UPDATE stories SET last_seen_at = %s, card_count = %s, "
            "digest_ids_json = %s WHERE id = %s",
            (
                datetime.utcnow().isoformat(),
                card_count,
                json.dumps(digest_ids),
                story_id,
            ),
        )
    except Exception as e:
        logger.warning("[stories] update_story failed: %s", e)


def was_in_recent_digest(story_id: int, days: int, storage: Any) -> bool:
    """True if `story_id`'s last_seen_at is within `days` days of now."""
    if storage is None or not story_id:
        return False
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
    try:
        row = storage.fetchone(
            "SELECT last_seen_at FROM stories WHERE id = %s AND last_seen_at >= %s",
            (story_id, cutoff),
        )
        return row is not None
    except Exception as e:
        logger.debug("[stories] was_in_recent_digest failed: %s", e)
        return False
