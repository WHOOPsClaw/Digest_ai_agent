"""Preset loader & resolver for LLM provider configs.

`presets.yaml` holds a curated list of cloud LLM providers. `resolve_llm_config()`
merges a user's llm config (from config.yaml) with the chosen preset to produce
a fully-resolved dict suitable for instantiating a provider.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

PRESETS_PATH = Path(__file__).parent / "presets.yaml"


@lru_cache(maxsize=1)
def load_presets() -> dict[str, dict]:
    """Load presets.yaml from the package. Cached."""
    if not PRESETS_PATH.exists():
        return {}
    with open(PRESETS_PATH) as f:
        data = yaml.safe_load(f) or {}
    return data


def get_preset(preset_id: str) -> dict | None:
    """Return the preset entry or None if not found."""
    return load_presets().get(preset_id)


def get_default_preset_id() -> str:
    """Return the preset flagged as default (or 'groq' as fallback)."""
    for pid, entry in load_presets().items():
        if entry.get("default"):
            return pid
    return "groq"


def _recommended_model(preset: dict) -> dict | None:
    models = preset.get("models") or []
    for m in models:
        if m.get("recommended"):
            return m
    return models[0] if models else None


def _find_model(preset: dict, model_id: str) -> dict | None:
    for m in preset.get("models") or []:
        if m.get("id") == model_id:
            return m
    return None


def resolve_llm_config(llm_cfg: Any) -> dict:
    """Merge preset + user overrides into a single dict.

    `llm_cfg` may be a pydantic LLMConfig, a plain dict, or None. Returns a dict
    with keys: provider, base_url, model, api_key, temperature, max_tokens,
    headers, params, cost_in, cost_out, preset_id, model_name.
    """
    if llm_cfg is None:
        cfg: dict = {}
    elif hasattr(llm_cfg, "model_dump"):
        cfg = llm_cfg.model_dump()
    elif isinstance(llm_cfg, dict):
        cfg = dict(llm_cfg)
    else:
        cfg = {
            k: getattr(llm_cfg, k)
            for k in (
                "preset", "provider", "base_url", "api_key", "model",
                "temperature", "max_tokens", "headers", "params",
            )
            if hasattr(llm_cfg, k)
        }

    preset_id = cfg.get("preset")
    preset = get_preset(preset_id) if preset_id else None

    resolved: dict[str, Any] = {
        "preset_id": preset_id,
        "provider": cfg.get("provider"),
        "base_url": cfg.get("base_url"),
        "api_key": cfg.get("api_key"),
        "model": cfg.get("model"),
        "temperature": cfg.get("temperature", 0.7),
        "max_tokens": cfg.get("max_tokens", 400),
        "headers": dict(cfg.get("headers") or {}),
        "params": dict(cfg.get("params") or {}),
        "cost_in": 0.0,
        "cost_out": 0.0,
        "model_name": None,
    }

    if preset:
        resolved["provider"] = resolved["provider"] or preset.get("provider")
        resolved["base_url"] = resolved["base_url"] or preset.get("base_url")

        model_id = resolved["model"]
        model_entry = _find_model(preset, model_id) if model_id else None
        if model_entry is None:
            model_entry = _recommended_model(preset)
        if model_entry:
            resolved["model"] = resolved["model"] or model_entry.get("id")
            resolved["model_name"] = model_entry.get("name")
            resolved["cost_in"] = float(model_entry.get("cost_in", 0) or 0)
            resolved["cost_out"] = float(model_entry.get("cost_out", 0) or 0)

    # Expand API key from env if it looks like ${VAR} or is missing.
    api_key = resolved.get("api_key") or ""
    if isinstance(api_key, str) and api_key.startswith("${") and api_key.endswith("}"):
        resolved["api_key"] = os.environ.get(api_key[2:-1], "")
    elif not api_key and preset_id:
        # Try conventional env names: NEWSBRIEF_<PRESET>_API_KEY or <PRESET>_API_KEY.
        for env_name in (
            f"NEWSBRIEF_{preset_id.upper()}_API_KEY",
            f"{preset_id.upper()}_API_KEY",
        ):
            if env_name in os.environ:
                resolved["api_key"] = os.environ[env_name]
                break

    return resolved
