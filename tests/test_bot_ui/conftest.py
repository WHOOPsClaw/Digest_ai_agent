"""Shared fixtures for bot UI tests: in-memory storage + fresh config."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from newsbrief.config import NewsbriefConfig, TopicConfig


@pytest.fixture
def storage(tmp_path, monkeypatch):
    """Isolated SQLite StorageAdapter pointing at a tmp file."""
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")

    # Force a fresh singleton
    import newsbrief.core.storage as st_mod
    st_mod._storage = None

    adapter = st_mod.StorageAdapter()
    adapter.ensure_schema()
    return adapter


@pytest.fixture
def config(tmp_path, monkeypatch):
    """A writable NewsbriefConfig saved to tmp_path/config.yaml."""
    cfg_path = tmp_path / "config.yaml"
    cfg = NewsbriefConfig()
    cfg.topics.append(TopicConfig(id="ai_ml", name="AI и агенты", emoji="🤖"))
    cfg.topics.append(TopicConfig(id="fin",   name="Финансы",     emoji="💰"))

    # Run tests with tmp_path as CWD so cfg.save() (default "config.yaml")
    # writes to an isolated location.
    monkeypatch.chdir(tmp_path)
    return cfg
