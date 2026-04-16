# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - TBD

### Added

- Initial release.
- **6 source types**: RSS/Atom, Telegram (public channels), Reddit, HackerNews, YouTube, Search (SearXNG / Brave / DuckDuckGo).
- **8 LLM presets**: Groq (default, free), Gemini, Cerebras, Mistral, OpenAI, Anthropic, DeepSeek, OpenRouter.
- **Source Discovery Agent** — LLM keyword extractor + curated DB of 100+ vetted sources + web search fallback.
- **Telegram delivery** with inline feedback buttons (👍 👎 🔕 📌).
- **Smart scheduling** — user-set `send_at`, auto-calculated `build_at` with per-provider floor and 7-day rolling p90 adaptive buffer. Multi-block schedules and weekend overrides.
- **Bot UI** — `/menu` inline keyboard with 10 settings screens (Schedule, LLM, Sources, Profile, Format, Notifications, Stats, Pause, Diagnostics, Reset).
- **CLI**: `setup`, `doctor`, `discover`, `schedule`, `validate`, `dry-run`, `run`, `daemon`, `llm`, `sources`, `stats`, `pause`, `resume`, `version`.
- **Feedback collection** — ratings train the filter LLM for subsequent digests.
- **Plugin system** — custom sources, LLM providers, and delivery channels loadable from `~/.newsbrief/plugins/` or entry points.
- **SQLite** (default) and **Postgres** support for persistence.
- **Docker Compose** deployment.
- **Custom prompts** — override `synthesis`, `filter`, `discovery`, and per-topic prompts via `config.yaml`.
- **Internationalisation** — output in `user.language` (English, Russian tested; others best-effort).
- 182 automated tests.

[Unreleased]: https://github.com/newsbrief/newsbrief/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/newsbrief/newsbrief/releases/tag/v0.1.0
