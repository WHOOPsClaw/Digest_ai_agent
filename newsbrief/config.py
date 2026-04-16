"""config.py — pydantic model for config.yaml.

Loads config from config.yaml + .env, validates, provides defaults.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field


class UserConfig(BaseModel):
    name: str = "User"
    language: str = "ru"
    timezone: str = "Europe/Moscow"
    profile: str = ""


class SourceSpec(BaseModel):
    """Generic source spec — type-specific fields in extra."""
    type: str
    config: dict = Field(default_factory=dict)


class TopicConfig(BaseModel):
    id: str
    name: str
    emoji: str = "📰"
    sources: dict = Field(default_factory=dict)
    interests_boost: list[str] = Field(default_factory=list)
    blacklist: list[str] = Field(default_factory=list)
    items_per_digest: int = 5
    fetch_limit_per_source: int = 25
    max_articles_total: int = 300


class ScheduleConfig(BaseModel):
    send_at: str = "09:00"
    build_buffer_minutes: Optional[int] = None  # auto if None
    build_at: Optional[str] = None  # auto if None
    timezone: str = "Europe/Moscow"


class SingleLLMConfig(BaseModel):
    """One configured LLM provider (one of many)."""
    preset: Optional[str] = None
    provider: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None
    display_name: Optional[str] = None  # user-friendly label
    temperature: float = 0.7
    max_tokens: int = 400
    headers: dict = Field(default_factory=dict)
    params: dict = Field(default_factory=dict)


class LLMConfig(BaseModel):
    """Multi-provider LLM configuration.

    New format uses ``providers`` (dict id → SingleLLMConfig) plus an
    ``active`` pointer. The top-level ``preset``/``api_key``/… fields remain
    for backward compatibility with single-provider configs.
    """
    active: str = "default"
    providers: dict[str, SingleLLMConfig] = Field(default_factory=dict)
    # Backward compat (old single-provider configs):
    preset: Optional[str] = "groq"
    provider: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 400
    headers: dict = Field(default_factory=dict)
    params: dict = Field(default_factory=dict)
    # Multi-provider routing
    routing: Optional[dict] = None
    # Rate-limit / throughput controls
    serial: bool = False                    # force single-threaded synthesis
    request_delay_sec: float = 0.0          # sleep between requests

    def resolve_active(self) -> dict:
        """Return the currently active provider config as a plain dict.

        If ``providers`` is populated, return the entry at ``active`` (or the
        first provider if ``active`` is missing). Otherwise fall back to the
        legacy top-level fields.
        """
        if self.providers:
            spec = self.providers.get(self.active)
            if spec is None:
                self.active = next(iter(self.providers))
                spec = self.providers[self.active]
            return spec.model_dump()
        return {
            "preset": self.preset,
            "provider": self.provider,
            "base_url": self.base_url,
            "api_key": self.api_key,
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "headers": dict(self.headers or {}),
            "params": dict(self.params or {}),
        }


class TelegramConfig(BaseModel):
    bot_token: str = ""
    chat_id: str = ""


class DeliveryConfig(BaseModel):
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)


class FormatConfig(BaseModel):
    items_per_topic: int = 5
    total_items_max: int = 30
    card_style: str = "medium"  # short | medium | detailed
    blockquote_why: bool = True
    include_editor_take: bool = False
    feedback_buttons: bool = False  # inline 👍👎🔕📌 buttons on cards (disabled by default)
    images: bool = True  # show article images (link previews) in Telegram cards


class FiltersConfig(BaseModel):
    semantic_exclude: list[str] = Field(default_factory=list)
    semantic_include: list[str] = Field(default_factory=list)
    enabled: bool = False


class BlockConfig(BaseModel):
    """One named interest block with its own schedule, topic subset, and card style."""
    name: str
    time: str = "09:00"                           # "HH:MM" or "mon 09:00" for weekly
    topics: list[str] = Field(default_factory=list)
    card_style: str = "medium"


class LearningConfig(BaseModel):
    enabled: bool = True
    min_feedback: int = 10
    auto_blacklist_threshold: int = 3
    apply_frequency_days: int = 7


class DedupConfig(BaseModel):
    """Phase 6: smart deduplication + entity grouping."""
    cross_digest_days: int = 7
    entity_grouping: bool = True
    entity_threshold: float = 0.5
    semantic_similarity_threshold: float = 0.7
    min_sources_for_grouping: int = 2
    recent_story_days: int = 3
    use_llm_entities: bool = False


class NewsbriefConfig(BaseModel):
    user:     UserConfig = Field(default_factory=UserConfig)
    topics:   list[TopicConfig] = Field(default_factory=list)
    schedule: ScheduleConfig = Field(default_factory=ScheduleConfig)
    llm:      LLMConfig = Field(default_factory=LLMConfig)
    delivery: DeliveryConfig = Field(default_factory=DeliveryConfig)
    format:   FormatConfig = Field(default_factory=FormatConfig)
    filters:  FiltersConfig = Field(default_factory=FiltersConfig)
    learning: LearningConfig = Field(default_factory=LearningConfig)
    dedup:    DedupConfig = Field(default_factory=DedupConfig)
    blocks:   list[BlockConfig] = Field(default_factory=list)
    prompts:  dict = Field(default_factory=dict)

    @classmethod
    def load(cls, path: str = "config.yaml") -> "NewsbriefConfig":
        if not Path(path).exists():
            return cls()
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        data = _expand_env(data)
        cfg = cls.model_validate(data)
        # Auto-migrate old single-provider configs to multi-provider.
        try:
            from newsbrief.llm.migration import migrate_single_to_multi
            cfg = migrate_single_to_multi(cfg)
        except Exception:
            pass
        return cfg

    def save(self, path: str = "config.yaml") -> None:
        data = self.model_dump(exclude_none=True)
        with open(path, "w") as f:
            yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


def _expand_env(obj: Any) -> Any:
    """Recursively replace ${VAR} with os.getenv(VAR)."""
    if isinstance(obj, str):
        if obj.startswith("${") and obj.endswith("}"):
            var = obj[2:-1]
            return os.getenv(var, "")
        return obj
    if isinstance(obj, dict):
        return {k: _expand_env(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_expand_env(x) for x in obj]
    return obj


def get_config(path: str = "config.yaml") -> NewsbriefConfig:
    return NewsbriefConfig.load(path)
