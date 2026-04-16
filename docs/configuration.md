# Configuration reference

Every option in `config.yaml` with defaults and examples.

`newsbrief` looks for `config.yaml` in:

1. `$NEWSBRIEF_CONFIG` (env var)
2. `./config.yaml` (current directory)
3. `~/.newsbrief/config.yaml`

Use `newsbrief validate` to check a config without running.

## Top-level structure

```yaml
user: { ... }
schedule: { ... }
llm: { ... }
delivery: { ... }
topics: [ ... ]
format: { ... }
filters: { ... }
prompts: { ... }
```

---

## `user`

Who the digest is for. Drives LLM personalisation.

```yaml
user:
  name: Ilya             # shown in greeting
  language: en           # ISO 639-1: en, ru, de, fr, es, pt, it, ja, zh
  timezone: Europe/Moscow
  profile: |
    I work on distributed systems in Rust.
    I'm interested in AI for code, indie games, and space news.
    Skip crypto and celebrity gossip.
```

| Field      | Type   | Default        | Notes                                               |
| ---------- | ------ | -------------- | --------------------------------------------------- |
| `name`     | string | `"You"`        | Used in greeting and prompt context                 |
| `language` | string | `en`           | Output language for summaries                       |
| `timezone` | string | `UTC`          | IANA tz name; used for `schedule`                   |
| `profile`  | string | `""`           | Free-text description — key personalisation signal  |

---

## `topics`

A list. Each topic becomes one message block in the digest.

```yaml
topics:
  - id: ai
    name: "AI & ML"
    emoji: "🤖"
    items_per_digest: 5
    interests_boost:
      - "open-weights models"
      - "RAG"
    blacklist:
      - "crypto"
      - "NFT"
    sources:
      rss:
        - https://simonwillison.net/atom/everything/
      telegram: [ai_newz, gonzo_ml]
      reddit: [MachineLearning, LocalLLaMA]
      hackernews: [top]
      youtube: []
      search:
        - "new LLM open-weights this week"
```

| Field              | Type       | Default | Notes                                                |
| ------------------ | ---------- | ------- | ---------------------------------------------------- |
| `id`               | string     | —       | Required, unique, snake_case                         |
| `name`             | string     | `id`    | Display name                                         |
| `emoji`            | string     | `📰`    | Displayed in Telegram block header                   |
| `items_per_digest` | int        | 5       | Overrides `format.items_per_topic` for this topic    |
| `interests_boost`  | list[str]  | `[]`    | Phrases that upweight candidate items                |
| `blacklist`        | list[str]  | `[]`    | Phrases that drop candidate items outright           |
| `sources`          | object     | `{}`    | See [sources.md](sources.md)                         |

---

## `schedule`

```yaml
schedule:
  send_at: "09:00"           # delivery time in local tz
  timezone: Europe/Moscow    # defaults to user.timezone
  build_at: auto             # or explicit "08:45"
  blocks:                    # optional multi-schedule
    - id: morning
      send_at: "07:30"
      topics: [world_news, tech]
    - id: evening
      send_at: "20:00"
      topics: [gaming, leisure]
```

| Field      | Type      | Default           | Notes                                                  |
| ---------- | --------- | ----------------- | ------------------------------------------------------ |
| `send_at`  | `HH:MM`   | `09:00`           | Delivery wall-clock time                               |
| `timezone` | string    | `user.timezone`   | IANA tz                                                |
| `build_at` | str/auto  | `auto`            | `auto` = `send_at - adaptive_buffer` (see scheduling)  |
| `blocks`   | list      | `[]`              | Multiple delivery blocks with topic subsets            |

See [scheduling.md](scheduling.md) for the adaptive buffer.

---

## `llm`

```yaml
llm:
  preset: groq
  # preset = shortcut; set any of the below to override
  provider: groq
  base_url: https://api.groq.com/openai/v1
  model: llama-3.3-70b-versatile
  api_key_env: GROQ_API_KEY
  # or:
  # api_key: gsk_xxxxx   (NOT recommended — prefer env var)

  routing:
    synthesis: groq          # big-context, creative
    filter: cerebras         # fast, cheap
    discovery: gemini        # web-grounded

  providers:
    cerebras:
      preset: cerebras
      api_key_env: CEREBRAS_API_KEY
    gemini:
      preset: gemini
      api_key_env: GEMINI_API_KEY
```

| Field         | Type   | Default            | Notes                                               |
| ------------- | ------ | ------------------ | --------------------------------------------------- |
| `preset`      | string | `groq`             | One of 8 presets in `data/presets.yaml`             |
| `provider`    | string | from preset        | openai-compatible endpoint tag                      |
| `base_url`    | string | from preset        | Override for self-hosted / proxies                  |
| `model`       | string | from preset        | Model slug                                          |
| `api_key_env` | string | from preset        | Env var name holding the key                        |
| `api_key`     | string | —                  | Inline key; prefer `api_key_env`                    |
| `routing`     | object | `{}`               | Per-task provider overrides                         |
| `providers`   | object | `{}`               | Named secondary providers (for routing)             |

Presets: `groq`, `gemini`, `cerebras`, `mistral`, `openai`, `anthropic`, `deepseek`, `openrouter`.

---

## `delivery`

```yaml
delivery:
  telegram:
    bot_token_env: TELEGRAM_BOT_TOKEN
    chat_id: 123456789
    parse_mode: HTML          # or MarkdownV2
    disable_web_page_preview: false
```

| Field                       | Type         | Default               | Notes                         |
| --------------------------- | ------------ | --------------------- | ----------------------------- |
| `bot_token_env`             | string       | `TELEGRAM_BOT_TOKEN`  | Env var with bot token        |
| `chat_id`                   | int / string | —                     | Required. Personal or channel |
| `parse_mode`                | string       | `HTML`                | `HTML` or `MarkdownV2`        |
| `disable_web_page_preview`  | bool         | `false`               | Per-message flag              |

---

## `format`

```yaml
format:
  items_per_topic: 5
  card_style: compact          # compact | full | headline
  blockquote_why: true
  show_source_domain: true
  show_read_time: true
  footer: "— newsbrief"
```

| Field                | Type   | Default     | Notes                                      |
| -------------------- | ------ | ----------- | ------------------------------------------ |
| `items_per_topic`    | int    | 5           | Global default for topics without override |
| `card_style`         | string | `compact`   | `compact`, `full`, or `headline`           |
| `blockquote_why`     | bool   | `true`      | Italicise "why it matters"                 |
| `show_source_domain` | bool   | `true`      | e.g. `(bbc.com)`                           |
| `show_read_time`     | bool   | `true`      | "~2 min read"                              |
| `footer`             | string | `""`        | Appended to every digest                   |

---

## `filters`

Semantic filters applied across all topics, after topic-level blacklist.

```yaml
filters:
  semantic_include:
    - "original reporting"
    - "primary sources"
  semantic_exclude:
    - "clickbait"
    - "opinion pieces without data"
```

These are soft signals passed to the filter LLM, not hard regex rules.

---

## `prompts`

Override any built-in prompt.

```yaml
prompts:
  synthesis: |
    You are a news analyst for a busy engineer.
    Be direct, skip marketing fluff, prefer concrete numbers.

  filter: |
    Drop any item that is press release, PR puffery,
    or rehashed content without new information.

  discovery: |
    Prefer independent blogs over corporate newsrooms.
```

See [custom-prompts.md](custom-prompts.md) for the full list of overridable prompts and variables available.

---

## Environment variables

These override `config.yaml` when set:

| Variable                 | Overrides                              |
| ------------------------ | -------------------------------------- |
| `NEWSBRIEF_CONFIG`       | config file path                       |
| `NEWSBRIEF_DATA_DIR`     | SQLite dir (default `./data`)          |
| `NEWSBRIEF_LOG_LEVEL`    | `debug` / `info` / `warning` / `error` |
| `TELEGRAM_BOT_TOKEN`     | `delivery.telegram.bot_token`          |
| `GROQ_API_KEY`           | `llm.api_key` when preset=groq         |
| `GEMINI_API_KEY`         | same                                   |
| `CEREBRAS_API_KEY`       | same                                   |
| `MISTRAL_API_KEY`        | same                                   |
| `OPENAI_API_KEY`         | same                                   |
| `ANTHROPIC_API_KEY`      | same                                   |
| `DEEPSEEK_API_KEY`       | same                                   |
| `OPENROUTER_API_KEY`     | same                                   |

## Minimal config

The smallest valid `config.yaml`:

```yaml
user:
  timezone: Europe/Moscow
llm:
  preset: groq
delivery:
  telegram:
    chat_id: 123456789
topics:
  - id: tech
    sources:
      hackernews: [top]
```

## See also

- [sources.md](sources.md) — source configuration
- [llm-providers.md](llm-providers.md) — provider details
- [examples/](examples/) — full configs for common use cases
