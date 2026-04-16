"""Tests for `newsbrief pause` and `newsbrief resume`."""
from __future__ import annotations

import os
import tempfile
from io import StringIO

import pytest
from rich.console import Console

from newsbrief.cli_pause import cmd_pause, cmd_resume
from newsbrief.core import pause as pause_mod


@pytest.fixture
def storage(monkeypatch):
    """Fresh SQLite storage in a temp file."""
    tmpdir = tempfile.mkdtemp(prefix="nb_pause_test_")
    db_path = os.path.join(tmpdir, "test.db")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    # Reset singleton so a new storage picks up the env var.
    import newsbrief.core.storage as storage_mod
    monkeypatch.setattr(storage_mod, "_storage", None)
    s = storage_mod.StorageAdapter()
    s.ensure_schema()
    return s


def test_pause_sets_state(storage):
    buf = StringIO()
    console = Console(file=buf, width=120, force_terminal=False)
    rc = cmd_pause(days=3, storage=storage, console=console)
    assert rc == 0
    assert "paused until" in buf.getvalue()
    assert pause_mod.is_paused(storage) is True


def test_resume_clears_state(storage):
    pause_mod.pause(storage, days=5)
    assert pause_mod.is_paused(storage)

    buf = StringIO()
    console = Console(file=buf, width=120, force_terminal=False)
    rc = cmd_resume(storage=storage, console=console)
    assert rc == 0
    assert "resumed" in buf.getvalue()
    assert pause_mod.is_paused(storage) is False


def test_is_paused_false_when_never_paused(storage):
    assert pause_mod.is_paused(storage) is False
    assert pause_mod.get_paused_until(storage) is None


def test_pause_invalid_days_rejected(storage):
    buf = StringIO()
    console = Console(file=buf, width=120, force_terminal=False)
    rc = cmd_pause(days=0, storage=storage, console=console)
    assert rc == 1
    assert pause_mod.is_paused(storage) is False


def test_pause_second_call_overwrites(storage):
    pause_mod.pause(storage, days=1)
    until1 = pause_mod.get_paused_until(storage)
    pause_mod.pause(storage, days=10)
    until2 = pause_mod.get_paused_until(storage)
    assert until2 > until1
