# Bot UI

Everything you can configure through Telegram without touching `config.yaml`.

Open the bot, send `/menu`.

## Main menu

```
🏠 newsbrief settings

  ⏰ Schedule        📡 Sources & topics
  🧠 LLM provider    👤 Profile
  🎨 Format          🔔 Notifications
  📊 Stats           ⏸ Pause
  🩺 Diagnostics     ♻️ Reset
```

Every button opens a sub-screen with its own inline keyboard.

<!-- ![Main menu](assets/menu.png) -->

---

## 1. Schedule

```
⏰ Schedule

Current: 09:00 (Europe/Moscow)
Next digest: tomorrow 09:00
Build time: 08:48 (auto)

  [07:00] [08:00] [09:00✓] [18:00] [21:00]
  [Custom time...]
  [Timezone]  [Days off]  [Blocks]
  [◀ Back]
```

- Presets post-to-chat instantly.
- Custom time → keyboard asks for `HH:MM`.
- Blocks → opens the multi-schedule editor.

## 2. LLM provider

```
🧠 LLM provider

Current: Groq (free tier) — llama-3.3-70b-versatile
Last test: ✓ 180ms

  [Groq✓] [Gemini] [Cerebras] [Mistral]
  [OpenAI] [Anthropic] [DeepSeek] [OpenRouter]
  [🧪 Test] [🔑 Set API key] [🎯 Routing]
  [◀ Back]
```

Selecting a provider without a key prompts:

```
Send /key <your-api-key>
or press [Skip] to cancel
```

Keys are stored in the secret store, never shown again.

## 3. Sources & topics

```
📡 Sources & topics

  [🤖 AI & ML (8)]      [⚙️ Programming (5)]
  [🎮 Gaming (3)]       [🌍 World news (6)]
  [➕ New topic]        [🔎 Discover]
  [◀ Back]
```

Tap a topic to edit:

```
🤖 AI & ML

Sources (8):
  1. ✓ simonwillison.net (RSS)
  2. ✓ jack-clark.net (RSS)
  3. ✓ @ai_newz (Telegram)
  ...

  [➕ Add source]  [🔎 Discover more]
  [Rename]  [Emoji]  [Items: 5]
  [Blacklist]  [Boost]
  [🗑 Delete topic]
  [◀ Back]
```

Dead sources (red ✗) can be retried or removed inline.

## 4. Profile

```
👤 Profile

Name:     Alex
Language: English
Timezone: Europe/Moscow
Interests:
  "AI research, Rust, indie games..."

  [Edit name] [Language] [Timezone]
  [✏️ Edit interests]
  [◀ Back]
```

Editing interests triggers an optional re-discovery pass.

## 5. Format

```
🎨 Format

Items per topic: 5
Card style:      compact ✓
Show "why":      yes
Source domain:   yes

  [3] [5✓] [8]  ← items per topic
  [compact✓] [full] [headline]
  [Why: on✓/off]
  [Domain: on✓/off]
  [◀ Back]
```

## 6. Notifications

```
🔔 Notifications

Silent delivery:   off
Preview links:     on
Reminder if you
skip 3 days:       on

  [Silent on/off] [Preview on/off]
  [Reminders on/off]
  [◀ Back]
```

## 7. Stats

```
📊 Stats — last 7 days

Digests delivered: 7 / 7
👍 useful:   12
👎 skip:      3
🔕 muted:     1 source
📌 saved:     4 items

Top topic: 🤖 AI & ML  (62% engagement)

  [14 days] [30 days] [All time]
  [Export CSV] [◀ Back]
```

## 8. Pause

```
⏸ Pause

Status: active

  [Pause 1 day] [Pause 3 days] [Pause 1 week]
  [Pause until date...]
  [Pause forever]
  [◀ Back]
```

Paused state blocks deliveries but doesn't stop builds (stats continue).

## 9. Diagnostics

```
🩺 Diagnostics

✓ Bot reachable
✓ chat_id OK
✓ LLM (groq): 180ms
✓ 22/24 sources OK
✗ 2 sources failing:
   - oldblog.example.com (404)
   - deadchannel (telegram)

  [Re-run] [Fix dead sources]
  [Send test digest]
  [◀ Back]
```

Equivalent to `newsbrief doctor` on the CLI.

## 10. Reset

```
♻️ Reset

This will:
  - delete config.yaml
  - keep the database
  - restart the setup wizard

Are you sure?

  [✅ Yes, reset]  [❌ Cancel]
```

Confirming runs the setup wizard in Telegram (same 5 questions as CLI).

## Inline actions on every digest

Each item in a digest has four inline buttons:

```
👍 useful   👎 skip   🔕 mute source   📌 save
```

- 👍 / 👎 — trains the filter for future digests
- 🔕 — adds source to that topic's blacklist
- 📌 — stores in "saved" list (view via `/saved`)

## Shortcuts

| Command      | Effect                          |
| ------------ | ------------------------------- |
| `/menu`      | Open main menu                  |
| `/digest`    | Build + send a digest now       |
| `/pause`     | Quick pause                     |
| `/resume`    | Quick resume                    |
| `/schedule`  | Shortcut to schedule screen     |
| `/stats`     | Shortcut to stats screen        |
| `/saved`     | List saved items                |
| `/help`      | Command reference               |
