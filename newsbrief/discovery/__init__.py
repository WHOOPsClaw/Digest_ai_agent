"""Source Discovery Agent — matches user interests to curated sources."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from newsbrief.discovery.matcher import match_interests
from newsbrief.discovery.validator import validate_source
from newsbrief.discovery.yaml_gen import generate_topics_yaml

__all__ = [
    "match_interests",
    "validate_source",
    "generate_topics_yaml",
    "load_known_sources",
    "KNOWN_SOURCES_PATH",
]


def _find_known_sources() -> Path:
    # Look in <repo>/data/known_sources.yaml relative to package.
    pkg_dir = Path(__file__).resolve().parent.parent  # newsbrief/
    candidate = pkg_dir.parent / "data" / "known_sources.yaml"
    return candidate


KNOWN_SOURCES_PATH = _find_known_sources()


def load_known_sources(path: Path | str | None = None) -> dict[str, Any]:
    """Load and return the known_sources.yaml contents."""
    p = Path(path) if path else KNOWN_SOURCES_PATH
    with open(p) as f:
        return yaml.safe_load(f) or {}
