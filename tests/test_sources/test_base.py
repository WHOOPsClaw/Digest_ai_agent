"""Tests for the SourceProvider base + plugin loader."""
from __future__ import annotations

from pathlib import Path

from newsbrief.sources.base import (
    SourceProvider,
    all_providers,
    get_provider,
    load_plugins,
    register,
)


def test_builtin_providers_registered():
    ids = set(all_providers().keys())
    assert {"rss", "telegram", "reddit", "hackernews", "youtube", "search"} <= ids


def test_get_provider_returns_none_for_unknown():
    assert get_provider("does-not-exist") is None


def test_register_requires_provider_id():
    class Bad(SourceProvider):
        provider_id = ""
        def fetch(self, config, limit=20):
            yield from ()
    import pytest
    with pytest.raises(ValueError):
        register(Bad())


def test_load_plugins_missing_dir_ok(tmp_path):
    assert load_plugins(tmp_path / "missing") == []


def test_load_plugins_imports_py_file(tmp_path: Path):
    plug = tmp_path / "sources"
    plug.mkdir()
    (plug / "_skip.py").write_text("raise RuntimeError('should be skipped')\n")
    (plug / "myplug.py").write_text(
        "from newsbrief.sources.base import SourceProvider, register\n"
        "class P(SourceProvider):\n"
        "    provider_id='testplug'\n"
        "    def fetch(self, config, limit=20):\n"
        "        yield from ()\n"
        "register(P())\n"
    )
    loaded = load_plugins(plug)
    assert any("myplug" in n for n in loaded)
    assert get_provider("testplug") is not None
