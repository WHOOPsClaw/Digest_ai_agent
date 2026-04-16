# newsbrief

[![Tests](https://github.com/newsbrief/newsbrief/actions/workflows/tests.yml/badge.svg)](https://github.com/newsbrief/newsbrief/actions/workflows/tests.yml)
[![PyPI version](https://badge.fury.io/py/newsbrief.svg)](https://badge.fury.io/py/newsbrief)
[![Docker](https://img.shields.io/badge/docker-ghcr.io-blue)](https://ghcr.io/newsbrief/newsbrief)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

> Self-hosted AI-powered news digest for Telegram.
> From `git clone` to first digest in 5 minutes.

<!-- screenshot of Telegram digest -->
<!-- ![newsbrief digest](docs/assets/digest.png) -->

## Features

- 🆓 **Free by default** — works on Groq free tier ($0/month, no credit card)
- 🤖 **8 LLM providers** — Groq, Gemini, Cerebras, Mistral, OpenAI, Anthropic, DeepSeek, OpenRouter
- 📡 **6 source types** — RSS, Telegram, Reddit, HackerNews, YouTube, Search
- 🎯 **Source Discovery** — describe interests, get recommended sources from a curated DB of 100+
- ⏰ **Smart scheduling** — set delivery time, build time auto-calculated with adaptive buffer
- 📱 **Telegram UI** — all settings via inline keyboard, no YAML editing required
- 🔌 **Extensible** — plugin system for custom sources, LLMs, delivery channels
- 🔒 **Private** — self-hosted, your data stays on your server, bring your own API keys

## Quickstart (5 minutes)

```bash
git clone https://github.com/newsbrief/newsbrief && cd newsbrief
docker compose run --rm newsbrief setup
docker compose up -d
```

The setup wizard asks:

1. **Telegram bot token** — from [@BotFather](https://t.me/BotFather)
2. **Your chat_id** — auto-detected when you first message the bot
3. **LLM provider** — press Enter for Groq (free tier, no card)
4. **What are you interested in?** — free text, e.g. "AI research, Rust, indie games"
5. **What time?** — presets 07:00–22:00 or custom `HH:MM`

Tomorrow at your chosen time — the first digest arrives in Telegram.

See [docs/quickstart.md](docs/quickstart.md) for a step-by-step guide.

## Screenshots

<!-- ![Main menu](docs/assets/menu.png) -->
<!-- ![Digest card](docs/assets/card.png) -->
<!-- ![Settings screen](docs/assets/settings.png) -->

*Screenshots coming in v0.1.0 release.*

## Installation options

### Docker (recommended)

```bash
git clone https://github.com/newsbrief/newsbrief
cd newsbrief
docker compose run --rm newsbrief setup
docker compose up -d
```

Data lives in `./data/` (SQLite DB) and `./config.yaml`. Both are mounted into the container.

### Pip

```bash
pip install newsbrief
newsbrief setup
newsbrief daemon
```

Creates config in `~/.newsbrief/config.yaml` and SQLite in `~/.newsbrief/newsbrief.db`.

### Development

```bash
git clone https://github.com/newsbrief/newsbrief
cd newsbrief
python -m venv venv
./venv/bin/pip install -e '.[dev]'
./venv/bin/newsbrief setup
```

## LLM providers

| Provider    | Free tier | Cost (1M tok input/output)  | Default model                 | Get key                                                                       |
| ----------- | --------- | --------------------------- | ----------------------------- | ----------------------------------------------------------------------------- |
| Groq        | ✅ Yes     | $0 / $0 (free tier)         | `llama-3.3-70b-versatile`     | [console.groq.com](https://console.groq.com)                                  |
| Gemini      | ✅ Yes     | $0.075 / $0.30              | `gemini-2.0-flash`            | [aistudio.google.com](https://aistudio.google.com/apikey)                     |
| Cerebras    | ✅ Yes     | $0 / $0 (free tier)         | `llama3.3-70b`                | [cloud.cerebras.ai](https://cloud.cerebras.ai)                                |
| Mistral     | ✅ Yes     | $0.15 / $0.15               | `mistral-small-latest`        | [console.mistral.ai](https://console.mistral.ai)                              |
| OpenAI      | ❌ No      | $0.15 / $0.60 (gpt-4o-mini) | `gpt-4o-mini`                 | [platform.openai.com](https://platform.openai.com/api-keys)                   |
| Anthropic   | ❌ No      | $0.80 / $4.00 (haiku)       | `claude-3-5-haiku-latest`     | [console.anthropic.com](https://console.anthropic.com)                        |
| DeepSeek    | ❌ No      | $0.14 / $0.28               | `deepseek-chat`               | [platform.deepseek.com](https://platform.deepseek.com)                        |
| OpenRouter  | Partial   | Varies                      | `meta-llama/llama-3.3-70b`    | [openrouter.ai](https://openrouter.ai)                                        |

See [docs/llm-providers.md](docs/llm-providers.md) for the full comparison.

## Sources supported

- **RSS/Atom** — any feed URL
- **Telegram** — public channels (no auth needed)
- **Reddit** — subreddits via JSON API
- **HackerNews** — top, new, best
- **YouTube** — channel RSS (transcripts optional)
- **Search** — SearXNG / Brave / DuckDuckGo

See [docs/sources.md](docs/sources.md) for config and examples.

## Configuration

Most users: let `newsbrief setup` generate `config.yaml`.

Advanced users: edit `config.yaml` directly. See [docs/configuration.md](docs/configuration.md) for the full reference.

## Commands

| Command                 | Description                                           |
| ----------------------- | ----------------------------------------------------- |
| `newsbrief setup`       | Interactive first-run wizard                          |
| `newsbrief doctor`      | Diagnose config, API keys, sources, connectivity      |
| `newsbrief discover`    | Source Discovery Agent — find sources by interests    |
| `newsbrief schedule`    | Show / edit delivery schedule                         |
| `newsbrief validate`    | Validate `config.yaml` without running                |
| `newsbrief dry-run`     | Build digest, print to stdout (no Telegram send)      |
| `newsbrief run`         | Build digest once and deliver                         |
| `newsbrief daemon`      | Run scheduler in foreground (for systemd/docker)      |
| `newsbrief llm`         | List / test / switch LLM providers                    |
| `newsbrief sources`     | List / add / remove sources                           |
| `newsbrief stats`       | Show recent digest stats                              |
| `newsbrief pause`       | Pause deliveries                                      |
| `newsbrief resume`      | Resume deliveries                                     |
| `newsbrief version`     | Print version                                         |

## Bot commands

- `/menu` — settings inline keyboard (10 screens)
- `/digest` — trigger a digest right now
- `/stats` — weekly read/feedback stats
- `/pause`, `/resume` — toggle deliveries
- `/schedule` — change delivery time

See [docs/bot-ui.md](docs/bot-ui.md) for screenshots of every settings screen.

## Documentation

- [Quickstart](docs/quickstart.md) — 5-minute overview
- **Deployment manuals:**
  - [Deploy on local machine](docs/deploy-local.md) — macOS/Linux/WSL
  - [Deploy on VPS](docs/deploy-vps.md) — production ($4-6/mo)
- [Configuration reference](docs/configuration.md)
- [Sources](docs/sources.md)
- [LLM providers](docs/llm-providers.md)
- [Source Discovery](docs/discovery.md)
- [Scheduling](docs/scheduling.md)
- [Bot UI](docs/bot-ui.md)
- [Custom prompts](docs/custom-prompts.md)
- [Plugins](docs/plugins.md)
- [Example configs](docs/examples/)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) — bug reports, PRs, and new sources are welcome.

## License

MIT — see [LICENSE](LICENSE).
