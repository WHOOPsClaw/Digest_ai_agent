# Changelog

All notable changes are documented here. Format based on [Keep a Changelog](https://keepachangelog.com/).

## [0.2.0] — 2026-04-16

### Added
- **Rate-limit-aware LLM routing** — TokenBucket algorithm + exponential backoff on 429 errors. Respects provider limits (Groq 30 RPM, Gemini 15 RPM, Cerebras 30 RPM, etc.). Retry up to 4 times with delays 0/5/15/45 sec, honors `Retry-After` header.
- **Multi-provider LLM management** — store multiple configured providers (Groq + OpenAI + Anthropic + custom) in one config, switch active via Telegram `/menu → 🤖 LLM провайдер → Переключить`. New CLI subcommands: `newsbrief llm switch/add/remove`.
- **Smart deduplication** — entity-based grouping (3 articles about Tesla → 1 merged card with 3 sources). Cross-digest semantic dedup via trigram Jaccard (7-day history). Stories tracking table for long-running topic awareness.
- **Image extraction** — pulls images from RSS `media:thumbnail`, Reddit `preview.images`, YouTube thumbnails, Telegram `og:image`. New `format.images: bool = true` config.
- **SimHash fast dedup** — O(N log N) for N > 50 articles. Enables scaling to 15-20+ sources per topic.
- **Inverted-index event grouping** — replaces O(N²) Jaccard comparison with token-based candidate selection. 3-5× faster on large article sets.
- **Serial LLM mode** — `llm.serial: true` + `request_delay_sec` for rate-limit-sensitive providers.
- **Progress notifications** — Telegram message on pipeline start: "🔄 Собираю дайджест... (3-5 мин)".
- **Persistent reply keyboard** — always-visible buttons: 📰 Дайджест сейчас / ⚙️ Меню настроек / 🕐 Расписание.
- **Quality filter in composer** — drops garbage cards (raw markdown, untranslated English, HTML entities, sub-30-char stubs).
- **Bot polling inside `daemon`** — `/menu`, `/digest`, `/schedule` commands work out-of-the-box without webhook setup.

### Changed
- **Feedback buttons OFF by default** — 👍👎🔕📌 removed from card rendering. Infrastructure retained for future reactivation. Stats no longer show "top sources by likes".
- **Main menu simplified** — removed Диагностика, Сбросить, Пауза, Уведомления, Время доставки. Now 5 clean items: 🤖 LLM / 📰 Источники / 🎯 Профиль / 🎨 Формат / 📊 Статистика.
- **Config schema extended** — backward compatible. New sections: `dedup`, `filters`, `learning`, `llm.providers{}`, `llm.active`, `format.images`, `topics[].fetch_limit_per_source`, `topics[].max_articles_total`.

### Fixed
- Legacy imports (`_legacy_fetcher`) replaced with `core.models.RawArticle` — fixes import errors when extracting into standalone package.
- `fetch_all()` wrapper now uses new `SourceProvider` interface, no fallback to removed legacy code.
- Quality filter prevents rate-limited LLM responses from leaking as raw garbage into digest.

### Stats
- **296 tests passing** (was 238 in v0.1.0-alpha, +58 new)
- SQLite storage with Postgres optional
- Tested on macOS 14, Ubuntu 22.04 (VPS)

## [0.1.0-alpha] — 2026-04-16

Initial public release. See release notes.
