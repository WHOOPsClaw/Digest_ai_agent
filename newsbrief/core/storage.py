"""core/storage.py — SQLite-first storage with Postgres option.

Unified connection abstraction. Default is SQLite (zero-config).
For multi-user deployments use Postgres via DATABASE_URL env.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Optional

logger = logging.getLogger("newsbrief")

DEFAULT_SQLITE_PATH = "data/newsbrief.db"


def _db_url() -> str:
    return os.getenv("DATABASE_URL", f"sqlite:///{DEFAULT_SQLITE_PATH}")


def _ensure_sqlite_dir(path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)


class StorageAdapter:
    """Minimal query interface supporting both SQLite and Postgres."""

    def __init__(self) -> None:
        self.url = _db_url()
        self.is_postgres = self.url.startswith("postgres")
        if not self.is_postgres:
            # sqlite:///path
            self.sqlite_path = self.url.replace("sqlite:///", "", 1)
            _ensure_sqlite_dir(self.sqlite_path)

    @contextmanager
    def conn(self) -> Iterator[Any]:
        if self.is_postgres:
            import psycopg2
            c = psycopg2.connect(self.url)
            try:
                yield c
            finally:
                c.close()
        else:
            c = sqlite3.connect(self.sqlite_path)
            c.row_factory = sqlite3.Row
            try:
                yield c
            finally:
                c.close()

    def execute(self, sql: str, params: tuple = ()) -> None:
        with self.conn() as c:
            cur = c.cursor()
            cur.execute(self._adapt_sql(sql), params)
            c.commit()
            cur.close()

    def fetchall(self, sql: str, params: tuple = ()) -> list:
        with self.conn() as c:
            cur = c.cursor()
            cur.execute(self._adapt_sql(sql), params)
            rows = cur.fetchall()
            cur.close()
            return [dict(r) if hasattr(r, "keys") else r for r in rows]

    def fetchone(self, sql: str, params: tuple = ()) -> Optional[Any]:
        with self.conn() as c:
            cur = c.cursor()
            cur.execute(self._adapt_sql(sql), params)
            row = cur.fetchone()
            cur.close()
            return dict(row) if row and hasattr(row, "keys") else row

    def _adapt_sql(self, sql: str) -> str:
        """Translate %s → ? for SQLite."""
        if self.is_postgres:
            return sql
        return sql.replace("%s", "?")

    def ensure_schema(self) -> None:
        """Create all tables if not exist."""
        schema_parts = [
            # Articles — raw fetched items
            """CREATE TABLE IF NOT EXISTS articles (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                url          TEXT NOT NULL,
                url_hash     TEXT NOT NULL,
                title        TEXT NOT NULL,
                snippet      TEXT,
                category     TEXT,
                source       TEXT,
                published_at TIMESTAMP,
                role         TEXT DEFAULT 'source',
                fetched_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(url_hash, category)
            )""",
            "CREATE INDEX IF NOT EXISTS idx_articles_hash ON articles(url_hash)",
            "CREATE INDEX IF NOT EXISTS idx_articles_date ON articles(fetched_at DESC)",

            # Digests — sent digests history
            """CREATE TABLE IF NOT EXISTS digests (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                digest_date   DATE NOT NULL,
                item_count    INTEGER,
                full_text     TEXT,
                parts_count   INTEGER,
                metadata_json TEXT,
                created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                sent_at       TIMESTAMP
            )""",

            # Pipeline runs — timing and stats for adaptive scheduling
            """CREATE TABLE IF NOT EXISTS pipeline_runs (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                run_date        DATE NOT NULL,
                started_at      TIMESTAMP NOT NULL,
                finished_at     TIMESTAMP,
                duration_sec    REAL,
                fetch_sec       REAL,
                synthesize_sec  REAL,
                llm_provider    TEXT,
                llm_calls       INTEGER,
                item_count      INTEGER,
                status          TEXT DEFAULT 'running',
                error           TEXT
            )""",

            # Feedback — reactions on cards
            """CREATE TABLE IF NOT EXISTS feedback (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                digest_id   INTEGER,
                article_url TEXT,
                source      TEXT,
                rating      TEXT,
                user_id     TEXT,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""",

            # User state for Telegram bot FSM
            """CREATE TABLE IF NOT EXISTS bot_state (
                user_id       TEXT PRIMARY KEY,
                current_state TEXT,
                context_json  TEXT,
                updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""",
        ]

        with self.conn() as c:
            cur = c.cursor()
            for stmt in schema_parts:
                cur.execute(self._adapt_sql(stmt))
            c.commit()
            cur.close()
        logger.info("[storage] schema ensured (%s)", "postgres" if self.is_postgres else "sqlite")


# Singleton
_storage: Optional[StorageAdapter] = None


def get_storage() -> StorageAdapter:
    global _storage
    if _storage is None:
        _storage = StorageAdapter()
        _storage.ensure_schema()
    return _storage
