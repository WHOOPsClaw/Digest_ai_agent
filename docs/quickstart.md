# Quickstart

Get your first digest in under 5 minutes.

## Requirements

Choose one:

- **Docker** — Docker Engine 20.10+ and Docker Compose v2
- **Python** — Python 3.11 or newer, `pip`, a POSIX shell

You also need:

- A Telegram account (to receive digests)
- One LLM API key (Groq works free with no credit card)

## 1. Get a Telegram bot token

Open Telegram and message [@BotFather](https://t.me/BotFather):

```
/newbot
```

BotFather will ask for a name (shown to users) and a username (must end with `bot`, e.g. `my_newsbrief_bot`). After creation you get a token like:

```
7234567890:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

Copy it. Treat it like a password.

<!-- ![BotFather screenshot](assets/botfather.png) -->

Then open your new bot and press **Start** (or send `/start`). This lets `newsbrief` auto-detect your `chat_id`.

## 2. Get an LLM API key

For the free path, go to [console.groq.com](https://console.groq.com), sign in (Google/GitHub OK), and create an API key. It looks like:

```
gsk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

Other providers: see [llm-providers.md](llm-providers.md).

## 3. Install

### Docker

```bash
git clone https://github.com/newsbrief/newsbrief
cd newsbrief
docker compose run --rm newsbrief setup
```

### Pip

```bash
pip install newsbrief
newsbrief setup
```

## 4. Run `setup`

The wizard walks you through everything:

```
$ newsbrief setup

Welcome to newsbrief!

1/5 Telegram bot token: 7234567890:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
    ✓ Bot verified: @my_newsbrief_bot

2/5 Send any message to your bot now, then press Enter...
    ✓ Detected chat_id: 123456789

3/5 LLM provider [groq]:
    ✓ Using Groq (free tier)
    API key: gsk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
    ✓ Key works, model llama-3.3-70b-versatile

4/5 What are you interested in? (free text, one line)
    > AI research, Rust programming, indie games, space exploration
    ✓ Saved profile

    Run source discovery now? [Y/n]: Y
    ✓ Found 23 sources matching your interests across 4 topics

5/5 What time to receive the digest?
    [1] 07:00   [2] 08:00   [3] 09:00 (default)   [4] 18:00   [5] 21:00   [6] custom
    > 3
    ✓ Scheduled for 09:00 (Europe/Moscow)
    ✓ Build time auto: 08:45

Config written to: ./config.yaml
Database:          ./data/newsbrief.db

All set. Run:
    docker compose up -d
or
    newsbrief daemon
```

## 5. What the wizard wrote

`config.yaml` looks roughly like this:

```yaml
user:
  name: You
  language: en
  timezone: Europe/Moscow
  profile: "AI research, Rust programming, indie games, space exploration"

schedule:
  send_at: "09:00"
  timezone: Europe/Moscow

llm:
  preset: groq
  api_key_env: GROQ_API_KEY

delivery:
  telegram:
    bot_token_env: TELEGRAM_BOT_TOKEN
    chat_id: 123456789

topics:
  - id: ai
    name: "AI & ML"
    emoji: "🤖"
    sources:
      rss:
        - https://simonwillison.net/atom/everything/
        - https://jack-clark.net/feed/
      telegram: [ai_newz, gonzo_ml]
      hackernews: [top]
  # ... more topics
```

See [configuration.md](configuration.md) for every field.

## 6. Verify

```bash
newsbrief doctor
```

Expected output:

```
✓ config.yaml valid
✓ Telegram bot reachable (@my_newsbrief_bot)
✓ chat_id 123456789 reachable
✓ LLM provider groq: OK (180ms)
✓ 12 sources reachable, 0 failed
✓ Database writable
✓ Scheduler configured: next build 08:45, next send 09:00
```

If something fails, `doctor` prints the fix.

## 7. First digest right now

Don't want to wait until tomorrow?

```bash
newsbrief dry-run   # print digest to stdout, no send
newsbrief run       # build and send once
```

Or from Telegram: send `/digest` to your bot.

## 8. Start the daemon

**Docker:**

```bash
docker compose up -d
docker compose logs -f
```

**Systemd / bare metal:**

```bash
newsbrief daemon
```

Or wrap in systemd — see [a systemd example](examples/newsbrief.service) once we ship one.

## What to expect in the first digest

- One message per topic
- 3–8 items per topic (configurable)
- Each item: headline, 1–2 sentence summary, "why it matters", source link
- Inline feedback buttons: 👍 useful · 👎 not for me · 🔕 mute source · 📌 save

The LLM's picks improve over a few days as it learns from your feedback.

## Troubleshooting

### "Telegram bot token invalid"

Re-check the token. Paste with no spaces. If still broken, create a fresh bot with BotFather.

### "chat_id not detected"

You must message the bot first (press Start). Then re-run `setup` or paste chat_id manually (get it from [@userinfobot](https://t.me/userinfobot)).

### "LLM provider returned 429 / 401"

- `401` → wrong API key. Run `newsbrief llm test groq` after fixing.
- `429` → rate limited. Free tiers have minute-level caps. Wait a minute, retry. For consistent use, consider Gemini free or a paid tier.

### "No items found for topic X"

Run `newsbrief sources --topic X --check`. Dead feeds are pruned automatically after 3 failed builds; you can add new ones via `newsbrief discover` or edit `config.yaml`.

### "Digest never arrives"

```bash
newsbrief doctor
newsbrief stats
docker compose logs newsbrief | tail -100
```

Common causes: daemon not running, timezone mismatch, `pause` still on (`/resume` in bot).

### Still stuck?

Open an issue with the output of `newsbrief doctor` attached. See [CONTRIBUTING.md](../CONTRIBUTING.md#filing-issues).

## Next steps

- [Configure sources and topics](configuration.md)
- [Run Source Discovery](discovery.md)
- [Customise prompts](custom-prompts.md)
- [Explore the bot UI](bot-ui.md)
