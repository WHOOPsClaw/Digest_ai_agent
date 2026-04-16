# Deployment Guide — Local Machine

Deploy `newsbrief` on your personal computer (macOS / Linux / Windows WSL). The digest agent runs in Docker, data stays on your disk.

> **Best for:** personal use, privacy, zero cost (Groq free tier), developer experimentation.

---

## Requirements

| Component | Version | Notes |
|-----------|---------|-------|
| OS | macOS 12+ / Linux / Windows 10+ (WSL2) | — |
| Docker Desktop | 4.25+ | Or Docker Engine 20.10+ on Linux |
| Docker Compose | v2 (plugin) | Bundled with Docker Desktop |
| Disk space | ~500 MB | Image + SQLite DB |
| RAM | 512 MB free | Default container limit |
| Internet | Outbound only | For LLM + RSS fetching |

Don't need: Python, package manager, admin/root access.

---

## Prerequisites

### 1. Telegram bot token

1. Open [@BotFather](https://t.me/BotFather) in Telegram
2. Send `/newbot`
3. Enter name (displayed): e.g. `My News Brief`
4. Enter username (must end with `bot`): e.g. `my_newsbrief_bot`
5. Copy the token: `7234567890:AAHxxxxxxx...`
6. Open your new bot → press **Start** (so the bot can see your chat_id)

### 2. Groq API key (free, no credit card)

1. Go to [console.groq.com](https://console.groq.com)
2. Sign up with Google or GitHub
3. Click **Create API Key**
4. Copy: `gsk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`

Alternative providers: see [llm-providers.md](llm-providers.md).

---

## Step-by-step deployment

### Step 1 — Clone

```bash
cd ~  # or wherever you keep projects
git clone https://github.com/newsbrief/newsbrief
cd newsbrief
```

Directory structure after clone:
```
newsbrief/
├── docker-compose.yml      # container config
├── Dockerfile              # image recipe
├── pyproject.toml          # Python package
├── newsbrief/              # source code
├── data/                   # (created at first run) SQLite DB
└── .env.example            # secrets template
```

### Step 2 — Run the setup wizard

```bash
docker compose run --rm newsbrief setup
```

First run builds the image (~1-2 minutes). Then the wizard asks 5 questions:

```
╔══════════════════════════════════════╗
║       newsbrief — setup wizard       ║
║   От 0 до первого дайджеста за 5 мин ║
╚══════════════════════════════════════╝

━━━ 1. Telegram Bot Token ━━━
Token: 7234567890:AAHxxxxxxx...

━━━ 2. Твой chat_id ━━━
Готов? Ждать сообщения 60 секунд? Y
  → Write anything to your bot in Telegram (e.g. /start)
✅ chat_id получен: 215493780

━━━ 3. LLM провайдер ━━━
? Какой LLM?
  ❯ Groq (БЕСПЛАТНО, Llama 3.3 70B) ⭐ рекомендую
    Gemini (БЕСПЛАТНО)
    ...
🔑 Вставь API key: gsk_xxx...
✅ Groq connected (latency 412ms)

━━━ 4. Интересы ━━━
> AI coding agents, Tesla autopilot, Russian politics, AAA games

🔍 Source Discovery running...
✨ Found 4 matching topics:
  [x] AI and Coding Agents (12 sources)
  [x] Tech & Startups (8 sources)
  [x] Russia (10 sources)
  [x] Gaming (6 sources)
Apply? Y

━━━ 5. Время доставки ━━━
? Во сколько получать дайджест?
  ❯ 10:00 — after wake up ⭐

✅ Config saved to config.yaml
✅ Secrets saved to .env

🔧 Checking connections...
✅ config.yaml valid
✅ Storage OK (SQLite)
✅ Telegram OK — @my_newsbrief_bot
✅ LLM connected: groq

✅ Done! Run: docker compose up -d
```

### Step 3 — Start the daemon

```bash
docker compose up -d
```

Container runs in background. Check status:
```bash
docker compose ps
docker compose logs -f newsbrief
```

### Step 4 — Verify

```bash
docker compose exec newsbrief newsbrief doctor
```

Expected:
```
✅ config.yaml valid
✅ Storage OK (SQLite, 24 KB)
✅ Telegram OK — @my_newsbrief_bot
✅ LLM groq — working (412ms)
✅ All sources reachable (36/36)
✅ Scheduler running — next: tomorrow 09:30 (build)
```

### Step 5 — Send a test digest right now

```bash
docker compose exec newsbrief newsbrief run
```

Pipeline takes 30-60 seconds with Groq. Digest arrives in Telegram.

---

## What the daemon does

Once `docker compose up -d` is running:

| Time (Moscow) | Job |
|---------------|-----|
| Daily 09:30   | Build digest (fetch → filter → synth) |
| Daily 10:00   | Send to Telegram |

Schedule is configurable — use `/menu → 🕐 Время доставки` in Telegram, or:
```bash
docker compose exec newsbrief newsbrief schedule
```

---

## File locations

| File | Purpose | Backup? |
|------|---------|---------|
| `config.yaml` | All settings (topics, schedule, LLM preset) | Yes |
| `.env` | Secrets (tokens, API keys) | Secure backup |
| `data/newsbrief.db` | SQLite: digests history, feedback, pipeline runs | Yes |
| `data/` | Volume — persists across container restarts | Yes |

Backup everything:
```bash
docker compose exec newsbrief newsbrief backup
# Creates: backups/newsbrief-YYYY-MM-DD-HHMMSS.tar.gz
```

---

## Day-to-day management

All settings through Telegram bot:

1. Send `/menu` to your bot → inline keyboard appears
2. Choose category:
   - 🕐 Change delivery time
   - 🤖 Switch LLM provider
   - 📰 Add/remove sources
   - 🎯 Update interests
   - 🎨 Digest format
   - ⏸ Pause / resume
   - 📊 Statistics

Or via CLI:
```bash
docker compose exec newsbrief newsbrief sources list
docker compose exec newsbrief newsbrief stats --days 30
docker compose exec newsbrief newsbrief pause --days 7
docker compose exec newsbrief newsbrief resume
```

---

## Updating

```bash
cd ~/newsbrief
git pull
docker compose build
docker compose down
docker compose up -d
```

Or with `install.sh` helper:
```bash
./scripts/install.sh   # pulls + rebuilds
```

Config and data survive updates.

---

## Stopping

```bash
docker compose down           # stop container, keep data
docker compose down -v        # stop + WIPE DATA (be careful)
```

---

## Troubleshooting

### Docker daemon not running (macOS)
Open Docker Desktop app. Wait for green status.

### Port 8080 already in use
Edit `docker-compose.yml`:
```yaml
ports:
  - "127.0.0.1:9090:8080"   # change 8080 → 9090
```

### "Cannot connect to Docker daemon"
```bash
sudo systemctl start docker          # Linux
open -a Docker                       # macOS
```

### chat_id not auto-detected
Manually get it:
1. Open [@userinfobot](https://t.me/userinfobot)
2. Send `/start`
3. Use the ID it returns

Then: `docker compose exec newsbrief newsbrief doctor` to verify.

### Logs
```bash
docker compose logs -f newsbrief
docker compose exec newsbrief newsbrief logs --pipeline
```

### Complete reset
```bash
docker compose down -v
rm config.yaml .env
docker compose run --rm newsbrief setup   # start over
```

---

## Uninstall

```bash
docker compose down -v         # stops + removes container + volume
cd ..
rm -rf newsbrief/              # removes source
```

Revoke tokens:
- Telegram: [@BotFather](https://t.me/BotFather) → `/revoke`
- Groq: [console.groq.com](https://console.groq.com) → delete key

---

## Next steps

- [Configuration reference](configuration.md) — all YAML options
- [Source Discovery](discovery.md) — how sources are picked
- [Bot UI](bot-ui.md) — Telegram settings screens
