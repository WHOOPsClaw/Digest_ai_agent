"""Tests for `newsbrief pause` / `newsbrief resume` via core.pause module."""
from __future__ import annotations

import os

import pytest

from newsbrief.core import pause as pause_mod
from newsbrief.core.storage import StorageAdapter


@pytest.fixture
def storage(tmp_path, monkeypatch):
    db = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    # Force a fresh adapter (the global singleton won't see the env change).
    s = StorageAdapter()
    s.ensure_schema()
    return s


def test_pause_sets_state(storage):
    assert pause_mod.is_paused(storage) is False
    until = pause_mod.pause(storage, days=3)
    assert pause_mod.is_paused(storage) is True
    assert pause_mod.get_paused_until(storage) == until


def test_resume_clears_state(storage):
    pause_mod.pause(storage, days=5)
    assert pause_mod.is_paused(storage) is True
    pause_mod.resume(storage)
    assert pause_mod.is_paused(storage) is False
    assert pause_mod.get_paused_until(storage) is None


def test_pause_reset(storage):
    pause_mod.pause(storage, days=1)
    new_until = pause_mod.pause(storage, days=10)
    assert pause_mod.get_paused_until(storage) == new_until
