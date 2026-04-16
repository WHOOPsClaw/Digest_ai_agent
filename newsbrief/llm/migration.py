"""Migration helpers for LLM config.

Transforms an old single-provider config (root-level ``llm.preset``, ``llm.api_key`` …)
into the new multi-provider format (``llm.providers[id]`` + ``llm.active``).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from newsbrief.config import NewsbriefConfig


def migrate_single_to_multi(cfg: "NewsbriefConfig") -> "NewsbriefConfig":
    """Auto-migrate old single-provider config → multi-provider.

    If ``llm.providers`` is already populated, returns ``cfg`` unchanged.
    If ``llm.preset`` (or other legacy fields) is set, copy them into
    ``providers['default']`` and set ``active='default'``.
    """
    llm = cfg.llm
    if llm.providers:
        # Already multi-provider. Ensure `active` points to a real entry.
        if llm.active not in llm.providers:
            llm.active = next(iter(llm.providers))
        return cfg

    # Only migrate when meaningful legacy data is present: an API key, a base
    # URL, a model, or a non-default provider. A bare ``preset: groq`` (the
    # library default) is not enough — we don't want to auto-spawn a phantom
    # "default" provider in fresh configs.
    has_any = any([llm.api_key, llm.base_url, llm.model, llm.provider])
    if not has_any:
        return cfg

    from newsbrief.config import SingleLLMConfig

    default_id = "default"
    spec = SingleLLMConfig(
        preset=llm.preset,
        provider=llm.provider,
        base_url=llm.base_url,
        api_key=llm.api_key,
        model=llm.model,
        display_name=llm.preset or "Default",
        temperature=llm.temperature,
        max_tokens=llm.max_tokens,
        headers=dict(llm.headers or {}),
        params=dict(llm.params or {}),
    )
    llm.providers = {default_id: spec}
    llm.active = default_id
    return cfg
