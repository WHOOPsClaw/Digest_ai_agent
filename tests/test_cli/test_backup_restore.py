"""Tests for backup/restore round-trip."""
from __future__ import annotations

from pathlib import Path

import pytest

from newsbrief.utils import backup as backup_mod


def test_backup_and_restore_roundtrip(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    # Seed config.yaml and data/
    Path("config.yaml").write_text("user:\n  name: Alice\n", encoding="utf-8")
    data = Path("data")
    data.mkdir()
    (data / "newsbrief.db").write_bytes(b"SQLITE-FAKE-BYTES")

    # Backup
    archive = backup_mod.create_backup(output=str(tmp_path / "bk.tar.gz"))
    assert Path(archive).exists()

    # Wipe and restore
    Path("config.yaml").unlink()
    (data / "newsbrief.db").unlink()
    data.rmdir()

    backup_mod.restore_backup(archive, target_dir=str(tmp_path))

    assert Path("config.yaml").read_text() == "user:\n  name: Alice\n"
    assert (Path("data") / "newsbrief.db").read_bytes() == b"SQLITE-FAKE-BYTES"


def test_restore_missing_archive_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        backup_mod.restore_backup(str(tmp_path / "nope.tar.gz"))
