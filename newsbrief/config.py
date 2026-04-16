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


class ScheduleConfig(BaseModel):
    send_at: str = "09:00"
    build_buffer_minutes: Optional[int] = None  # auto if None
    build_at: Optional[str] = None  # auto if None
    timezone: str = "Europe/Moscow"


class LLMConfig(BaseModel):
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
    providers: Optional[dict] = None


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


class NewsbriefConfig(BaseModel):
    user:     UserConfig = Field(default_factory=UserConfig)
    topics:   list[TopicConfig] = Field(default_factory=list)
    schedule: ScheduleConfig = Field(default_factory=ScheduleConfig)
    llm:      LLMConfig = Field(default_factory=LLMConfig)
    delivery: DeliveryConfig = Field(default_factory=DeliveryConfig)
    format:   FormatConfig = Field(default_factory=FormatConfig)
    filters:  FiltersConfig = Field(default_factory=FiltersConfig)
    learning: LearningConfig = Field(default_factory=LearningConfig)
    blocks:   list[BlockConfig] = Field(default_factory=list)
    prompts:  dict = Field(default_factory=dict)

    @classmethod
    def load(cls, path: str = "config.yaml") -> "NewsbriefConfig":
        if not Path(path).exists():
            return cls()
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        data = _expand_env(data)
        return cls.model_validate(data)

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
