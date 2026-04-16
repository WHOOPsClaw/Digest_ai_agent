"""Shared storage fixture for feedback tests."""
from __future__ import annotations

import pytest


@pytest.fixture
def storage(tmp_path, monkeypatch):
    db_path = tmp_path / "fb.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    import newsbrief.core.storage as st_mod
    st_mod._storage = None
    adapter = st_mod.StorageAdapter()
    adapter.ensure_schema()
    return adapter


def insert_feedback(storage, source: str, rating: str, n: int = 1, user_id: str = "u1") -> None:
    for _ in range(n):
        storage.execute(
            "INSERT INTO feedback (digest_id, article_url, source, rating, user_id) "
            "VALUES (%s, %s, %s, %s, %s)",
            (1, "idx:0", source, rating, user_id),
        )
