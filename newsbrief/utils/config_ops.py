"""Helpers for `newsbrief config` sub-commands."""
from __future__ import annotations

import copy
import json
import os
import subprocess
from pathlib import Path
from typing import Any

import yaml

SECRET_KEYS = {"api_key", "bot_token", "token", "password", "secret"}


def _redact(obj: Any) -> Any:
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if isinstance(k, str) and k.lower() in SECRET_KEYS and isinstance(v, str) and v:
                out[k] = "***REDACTED***"
            else:
                out[k] = _redact(v)
        return out
    if isinstance(obj, list):
        return [_redact(x) for x in obj]
    return obj


def load_raw(path: str = "config.yaml") -> dict:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(path)
    with open(p) as f:
        return yaml.safe_load(f) or {}


def redacted_yaml(path: str = "config.yaml") -> str:
    data = load_raw(path)
    red = _redact(copy.deepcopy(data))
    return yaml.safe_dump(red, allow_unicode=True, sort_keys=False)


def export_json(path: str = "config.yaml") -> str:
    data = load_raw(path)
    return json.dumps(data, indent=2, ensure_ascii=False)


def import_json(json_path: str, target: str = "config.yaml") -> None:
    with open(json_path) as f:
        data = json.load(f)
    with open(target, "w") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


def open_in_editor(path: str = "config.yaml") -> int:
    editor = os.environ.get("EDITOR", "vi")
    return subprocess.call([editor, path])
