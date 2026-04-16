"""Multi-provider LLM management API.

Functions operate on ``NewsbriefConfig`` (mutating ``config.llm``) and do not
persist by themselves — callers should call ``config.save()`` as appropriate.
"""
from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from newsbrief.llm.presets import get_preset, resolve_llm_config

if TYPE_CHECKING:  # pragma: no cover
    from newsbrief.config import NewsbriefConfig, SingleLLMConfig

logger = logging.getLogger("newsbrief")


def _ensure_providers_dict(config: "NewsbriefConfig") -> None:
    from newsbrief.llm.migration import migrate_single_to_multi
    migrate_single_to_multi(config)
    if not config.llm.providers:
        # Fresh config with no legacy data either — initialize empty.
        config.llm.providers = {}


def add_provider(config: "NewsbriefConfig", provider_id: str, spec: "SingleLLMConfig") -> None:
    """Register / update a provider under ``provider_id``."""
    from newsbrief.config import SingleLLMConfig as _S
    _ensure_providers_dict(config)
    if not isinstance(spec, _S):
        # Coerce from dict if needed.
        spec = _S.model_validate(spec) if isinstance(spec, dict) else spec
    config.llm.providers[provider_id] = spec
    if not config.llm.active or config.llm.active not in config.llm.providers:
        config.llm.active = provider_id


def remove_provider(config: "NewsbriefConfig", provider_id: str) -> bool:
    """Remove a provider. Returns True if removed."""
    _ensure_providers_dict(config)
    if provider_id not in config.llm.providers:
        return False
    del config.llm.providers[provider_id]
    if config.llm.active == provider_id:
        config.llm.active = next(iter(config.llm.providers), "")
    return True


def set_active(config: "NewsbriefConfig", provider_id: str) -> bool:
    """Switch the active provider. Returns True on success."""
    _ensure_providers_dict(config)
    if provider_id not in config.llm.providers:
        return False
    config.llm.active = provider_id
    return True


def list_providers(config: "NewsbriefConfig") -> list[dict]:
    """Return [{id, display_name, preset, model, active, status}] for each provider."""
    _ensure_providers_dict(config)
    out: list[dict] = []
    for pid, spec in config.llm.providers.items():
        preset = spec.preset or ""
        preset_entry = get_preset(preset) if preset else None
        preset_label = preset_entry.get("name") if preset_entry else preset
        out.append({
            "id": pid,
            "display_name": spec.display_name or preset_label or pid,
            "preset": preset,
            "model": spec.model or "",
            "active": pid == config.llm.active,
            "status": "ok" if (spec.api_key or preset == "ollama") else "missing_key",
        })
    return out


def test_provider(config: "NewsbriefConfig", provider_id: str) -> dict:
    """Run a quick generation against the given provider. Returns {ok, latency_ms, error}."""
    _ensure_providers_dict(config)
    spec = config.llm.providers.get(provider_id)
    if spec is None:
        return {"ok": False, "latency_ms": 0, "error": f"Unknown provider {provider_id!r}"}

    from newsbrief.llm.router import build_provider
    try:
        resolved = resolve_llm_config(spec.model_dump())
        provider = build_provider(resolved)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "latency_ms": 0, "error": f"build_provider: {e}"}

    t0 = time.time()
    try:
        result = provider.test()
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "latency_ms": int((time.time() - t0) * 1000), "error": str(e)}

    latency = int((time.time() - t0) * 1000)
    if isinstance(result, dict):
        return {
            "ok": bool(result.get("ok")),
            "latency_ms": result.get("latency_ms", latency),
            "error": result.get("error"),
        }
    return {"ok": bool(result), "latency_ms": latency, "error": None}


def test_all(config: "NewsbriefConfig") -> dict[str, dict]:
    """Run test() on every configured provider. Returns {id: result}."""
    _ensure_providers_dict(config)
    return {pid: test_provider(config, pid) for pid in config.llm.providers}
