"""CLI entry-points for `newsbrief llm` subcommand.

Commands:
  newsbrief llm list    — show presets + whether configured
  newsbrief llm test    — smoke-test configured LLM
  newsbrief llm setup   — interactive wizard: pick preset, enter API key, save
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from newsbrief.llm.presets import get_default_preset_id, load_presets, resolve_llm_config
from newsbrief.llm.router import LLMRouter


def _load_config() -> Any | None:
    try:
        from newsbrief.config import NewsbriefConfig
    except Exception:
        return None
    try:
        if hasattr(NewsbriefConfig, "load"):
            return NewsbriefConfig.load()
        return NewsbriefConfig()
    except Exception:
        return None


def cmd_list() -> int:
    """Print configured providers (if any) + available presets."""
    cfg = _load_config()
    # Configured providers first.
    if cfg is not None and getattr(cfg.llm, "providers", None):
        from newsbrief.llm.manager import list_providers
        print("Configured providers:\n")
        for p in list_providers(cfg):
            marker = " [ACTIVE]" if p["active"] else ""
            print(
                f"  {p['id']:12s} — {p['display_name']} "
                f"({p['model'] or 'default'}) [{p['status']}]{marker}"
            )
        print()

    presets = load_presets()
    current = None
    if cfg is not None:
        current = getattr(getattr(cfg, "llm", None), "preset", None)

    default_id = get_default_preset_id()

    print("Available LLM presets:\n")
    for pid, entry in presets.items():
        tag = []
        if pid == current:
            tag.append("CONFIGURED")
        if pid == default_id:
            tag.append("DEFAULT")
        suffix = f"  [{', '.join(tag)}]" if tag else ""
        print(f"  {pid:12s} — {entry.get('name', pid)}{suffix}")
        if entry.get("free_tier"):
            print(f"               free: {entry['free_tier']}")
        models = entry.get("models") or []
        rec = next((m for m in models if m.get("recommended")), models[0] if models else None)
        if rec:
            print(f"               recommended model: {rec.get('id')}")
        print()
    return 0


def cmd_test() -> int:
    cfg = _load_config()
    if cfg is None:
        print("No config found. Run `newsbrief llm setup` first.")
        return 1

    try:
        router = LLMRouter(cfg)
    except Exception as e:
        print(f"Failed to build LLM provider: {e}")
        return 1

    print("Testing LLM provider...")
    result = router.test()
    if result.get("ok"):
        print(f"OK  model={result.get('model')}  latency={result.get('latency_ms')}ms")
        return 0
    print(f"FAIL  error={result.get('error')}")
    return 1


def _prompt(question: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        ans = input(f"{question}{suffix}: ").strip()
    except EOFError:
        ans = ""
    return ans or default


def _save_api_key_to_env(env_name: str, value: str, env_path: str = ".env") -> None:
    path = Path(env_path)
    lines: list[str] = []
    if path.exists():
        lines = path.read_text().splitlines()
    replaced = False
    out = []
    for line in lines:
        if line.startswith(f"{env_name}="):
            out.append(f"{env_name}={value}")
            replaced = True
        else:
            out.append(line)
    if not replaced:
        out.append(f"{env_name}={value}")
    path.write_text("\n".join(out) + "\n")


def cmd_setup() -> int:
    presets = load_presets()
    if not presets:
        print("No presets available.")
        return 1

    ids = list(presets.keys())
    print("Pick a preset:")
    for i, pid in enumerate(ids, 1):
        entry = presets[pid]
        mark = " (default)" if entry.get("default") else ""
        print(f"  {i}. {pid} — {entry.get('name')}{mark}")

    default_id = get_default_preset_id()
    choice = _prompt("Enter number or preset id", default_id)

    pid = None
    if choice.isdigit() and 1 <= int(choice) <= len(ids):
        pid = ids[int(choice) - 1]
    elif choice in presets:
        pid = choice
    if not pid:
        print(f"Unknown choice: {choice}")
        return 1

    preset = presets[pid]
    print(f"\nSelected: {preset.get('name')}")
    if preset.get("api_key_url"):
        print(f"Get an API key here: {preset['api_key_url']}")

    api_key = _prompt("Paste API key")
    if not api_key:
        print("No API key entered. Aborting.")
        return 1

    # Pick model (first recommended).
    models = preset.get("models") or []
    rec = next((m for m in models if m.get("recommended")), models[0] if models else None)
    model_id = rec.get("id") if rec else ""

    env_name = f"NEWSBRIEF_{pid.upper()}_API_KEY"
    _save_api_key_to_env(env_name, api_key)
    os.environ[env_name] = api_key
    print(f"Saved {env_name} to .env")

    # Update config.yaml llm section if possible.
    try:
        from newsbrief.config import NewsbriefConfig
        cfg = NewsbriefConfig.load() if hasattr(NewsbriefConfig, "load") else NewsbriefConfig()
        cfg.llm.preset = pid
        cfg.llm.model = model_id
        cfg.llm.api_key = f"${{{env_name}}}"
        if hasattr(cfg, "save"):
            cfg.save()
            print("Updated config.yaml")
    except Exception as e:
        print(f"(config.yaml not updated: {e})")

    # Quick test.
    resolved = resolve_llm_config({
        "preset": pid, "model": model_id, "api_key": api_key,
    })
    print(f"Resolved: provider={resolved['provider']}  model={resolved['model']}")
    print("Run `newsbrief llm test` to verify.")
    return 0


def cmd_switch(provider_id: str) -> int:
    from newsbrief.llm.manager import set_active
    cfg = _load_config()
    if cfg is None:
        print("No config found.")
        return 1
    if not set_active(cfg, provider_id):
        print(f"Unknown provider: {provider_id!r}")
        return 1
    if hasattr(cfg, "save"):
        cfg.save()
    print(f"Active LLM provider → {provider_id}")
    return 0


def cmd_remove(provider_id: str) -> int:
    from newsbrief.llm.manager import remove_provider
    cfg = _load_config()
    if cfg is None:
        print("No config found.")
        return 1
    if not remove_provider(cfg, provider_id):
        print(f"Unknown provider: {provider_id!r}")
        return 1
    if hasattr(cfg, "save"):
        cfg.save()
    print(f"Removed provider: {provider_id}")
    return 0


def cmd_add(preset: str | None) -> int:
    """Interactive: add a new provider by preset."""
    from newsbrief.config import SingleLLMConfig
    from newsbrief.llm.manager import add_provider

    presets = load_presets()
    if preset is None:
        preset = _prompt("Preset id", get_default_preset_id())
    if preset not in presets and preset != "custom":
        print(f"Unknown preset: {preset!r}")
        return 1

    cfg = _load_config()
    if cfg is None:
        print("No config found. Run `newsbrief setup` first.")
        return 1

    base_url = None
    model = None
    if preset == "custom":
        base_url = _prompt("Base URL (OpenAI-compatible)")
        model = _prompt("Model name")
    else:
        entry = presets[preset]
        models = entry.get("models") or []
        rec = next((m for m in models if m.get("recommended")), models[0] if models else None)
        model = rec.get("id") if rec else None

    api_key = _prompt("API key")
    if not api_key:
        print("No API key — aborting.")
        return 1

    # Pick an id.
    provider_id = _prompt("Provider id (short)", preset)
    spec = SingleLLMConfig(
        preset=None if preset == "custom" else preset,
        provider="openai_compatible" if preset == "custom" else None,
        base_url=base_url,
        api_key=api_key,
        model=model,
        display_name=provider_id.title(),
    )
    add_provider(cfg, provider_id, spec)
    if hasattr(cfg, "save"):
        cfg.save()
    print(f"Added provider {provider_id!r} (active={cfg.llm.active})")
    return 0


def dispatch(subcmd: str | None, *, provider_id: str | None = None,
             preset: str | None = None) -> int:
    if subcmd == "list":
        return cmd_list()
    if subcmd == "test":
        return cmd_test()
    if subcmd == "setup":
        return cmd_setup()
    if subcmd == "switch":
        if not provider_id:
            print("Usage: newsbrief llm switch <provider_id>")
            return 1
        return cmd_switch(provider_id)
    if subcmd == "add":
        return cmd_add(preset)
    if subcmd == "remove":
        if not provider_id:
            print("Usage: newsbrief llm remove <provider_id>")
            return 1
        return cmd_remove(provider_id)
    print("Usage: newsbrief llm {list|test|setup|switch|add|remove}")
    return 1
