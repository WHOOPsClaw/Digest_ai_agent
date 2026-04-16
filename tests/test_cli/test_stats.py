"""Tests for `newsbrief stats`."""
from __future__ import annotations

from io import StringIO

from rich.console import Console

from newsbrief.cli_stats import cmd_stats


class FakeStorage:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def fetchall(self, sql: str, params: tuple = ()) -> list:
        self.queries.append(sql)
        if "FROM digests" in sql:
            return [{"n": 7, "items": 140}]
        if "FROM feedback" in sql and "GROUP BY rating" in sql:
            return [
                {"rating": "like", "n": 42},
                {"rating": "dislike", "n": 18},
                {"rating": "block", "n": 3},
                {"rating": "save", "n": 7},
            ]
        if "FROM feedback" in sql and "GROUP BY source" in sql:
            return [
                {"source": "rss:simonwillison.net", "n": 8},
                {"source": "reddit:LocalLLaMA", "n": 6},
            ]
        if "FROM pipeline_runs" in sql and "GROUP BY status" in sql:
            return [
                {"status": "ok", "n": 7, "avg_sec": 173.0, "calls": 980},
            ]
        return []

    def fetchone(self, sql: str, params: tuple = ()):
        if "FROM pipeline_runs" in sql:
            return {"avg_sec": 173.0}
        return None


def test_stats_happy_path():
    buf = StringIO()
    console = Console(file=buf, width=120, force_terminal=False)
    rc = cmd_stats(days=7, storage=FakeStorage(), console=console)
    out = buf.getvalue()
    assert rc == 0
    assert "Stats for last 7 days" in out
    assert "Digests sent: 7/7" in out
    assert "Total cards delivered: 140" in out
    assert "42" in out   # liked
    assert "18" in out   # disliked
    # Top-sources section removed in Phase 3
    assert "Succeeded: 7" in out
    assert "Failed: 0" in out


def test_stats_handles_empty_db():
    class Empty:
        def fetchall(self, sql, params=()): return []
        def fetchone(self, sql, params=()): return None

    buf = StringIO()
    console = Console(file=buf, width=120, force_terminal=False)
    rc = cmd_stats(days=30, storage=Empty(), console=console)
    assert rc == 0
    assert "Stats for last 30 days" in buf.getvalue()


def test_stats_days_param_used_in_header():
    buf = StringIO()
    console = Console(file=buf, width=120, force_terminal=False)
    cmd_stats(days=14, storage=FakeStorage(), console=console)
    assert "last 14 days" in buf.getvalue()
