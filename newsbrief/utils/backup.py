"""Backup/restore: tar.gz of config.yaml + data/ directory."""
from __future__ import annotations

import tarfile
from datetime import datetime
from pathlib import Path


def default_backup_path() -> str:
    ts = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    return f"backups/newsbrief-{ts}.tar.gz"


def create_backup(output: str | None = None,
                  config_path: str = "config.yaml",
                  data_dir: str = "data") -> str:
    out = output or default_backup_path()
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(out, "w:gz") as tar:
        if Path(config_path).exists():
            tar.add(config_path, arcname="config.yaml")
        if Path(data_dir).exists():
            tar.add(data_dir, arcname="data")
    return out


def restore_backup(archive: str, target_dir: str = ".") -> None:
    if not Path(archive).exists():
        raise FileNotFoundError(archive)
    with tarfile.open(archive, "r:gz") as tar:
        # Guard against path traversal.
        target = Path(target_dir).resolve()
        for member in tar.getmembers():
            dest = (target / member.name).resolve()
            if not str(dest).startswith(str(target)):
                raise RuntimeError(f"unsafe path in archive: {member.name}")
        tar.extractall(target_dir)
