"""Tests for `newsbrief config show/export/import` — secret redaction + round-trip."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from newsbrief.utils import config_ops


@pytest.fixture
def sample_config(tmp_path, monkeypatch):
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(
        "user:\n  name: Test\n"
        "llm:\n  preset: groq\n  api_key: sk-secret-1234\n"
        "delivery:\n  telegram:\n    bot_token: 123:ABCDEF\n    chat_id: '42'\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    return cfg_path


def test_config_show_redacts_secrets(sample_config):
    out = config_ops.redacted_yaml("config.yaml")
    assert "sk-secret-1234" not in out
    assert "123:ABCDEF" not in out
    assert "REDACTED" in out
    # Non-secret fields preserved
    assert "Test" in out
    assert "groq" in out


def test_config_export_is_valid_json(sample_config):
    out = config_ops.export_json("config.yaml")
    data = json.loads(out)
    assert data["user"]["name"] == "Test"
    assert data["llm"]["api_key"] == "sk-secret-1234"  # raw export not redacted


def test_config_import_roundtrip(sample_config, tmp_path):
    # Export JSON, wipe yaml, import back
    out = config_ops.export_json("config.yaml")
    json_path = tmp_path / "backup.json"
    json_path.write_text(out, encoding="utf-8")

    Path("config.yaml").unlink()
    config_ops.import_json(str(json_path), "config.yaml")

    raw = config_ops.load_raw("config.yaml")
    assert raw["user"]["name"] == "Test"
    assert raw["llm"]["api_key"] == "sk-secret-1234"
