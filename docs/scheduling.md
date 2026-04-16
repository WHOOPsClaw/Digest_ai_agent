# Scheduling

The scheduler has one job: **deliver a fresh digest at your chosen time**.

You set `send_at`. Everything else is computed.

## How `send_at` works

```yaml
schedule:
  send_at: "09:00"
  timezone: Europe/Moscow
```

At 09:00 local time every day, `newsbrief` posts the digest to Telegram. If the digest isn't ready yet, it waits up to 5 minutes, then posts what it has.

## How `build_at` is calculated

Building a digest takes time — fetch sources, filter, synthesise, format. So `newsbrief` starts **before** `send_at`.

```
build_at = send_at − build_buffer
```

`build_buffer` is computed per LLM provider:

| Provider    | Default buffer |
| ----------- | -------------- |
| Groq        | 10 min         |
| Cerebras    | 8 min          |
| Gemini      | 12 min         |
| Mistral     | 12 min         |
| OpenAI      | 15 min         |
| Anthropic   | 18 min         |
| DeepSeek    | 20 min         |
| OpenRouter  | 15 min         |

For `send_at: "09:00"` with Groq → `build_at = 08:50`.

To pin it manually:

```yaml
schedule:
  send_at: "09:00"
  build_at: "08:30"       # explicit
```

## Adaptive buffer

The default buffer is a starting point. `newsbrief` records how long each build actually takes and maintains a **7-day rolling p90**.

```
effective_buffer = max(provider_default, rolling_p90 + 2min safety)
```

So if your source list grows and builds take 14 minutes, the buffer widens automatically. If they speed up, it shrinks back (but never below the provider floor).

See the current buffer:

```bash
newsbrief schedule
```

```
Schedule (Europe/Moscow):
  send_at:        09:00
  build_at:       08:48   (auto)
  provider:       groq
  provider_floor: 10:00
  rolling p90:    11:23   (last 7 days)
  next build:     2026-04-16 08:48:00 +03:00
  next send:      2026-04-16 09:00:00 +03:00
```

## Interest blocks (multiple schedules)

Split your digest into blocks delivered at different times:

```yaml
schedule:
  timezone: Europe/Moscow
  blocks:
    - id: morning
      send_at: "07:30"
      topics: [world_news, tech]
    - id: lunch
      send_at: "13:00"
      topics: [programming]
    - id: evening
      send_at: "20:00"
      topics: [gaming, movies]
```

Each block builds independently with its own buffer. Topics not in any block go to the default `send_at` (if set) or are skipped.

## Pause / resume

```bash
newsbrief pause                 # stop deliveries
newsbrief pause --days 7        # stop for a week
newsbrief resume
```

Or from Telegram: `/pause`, `/resume`.

Paused state is persisted — surviving restarts.

## Weekend / weekday differences

```yaml
schedule:
  send_at: "07:30"
  weekend:
    send_at: "10:00"
  days_off: [saturday]          # no digest at all on Sat
```

## Timezone handling

- `schedule.timezone` is **authoritative** for `send_at` and `build_at`.
- If unset, falls back to `user.timezone`.
- If both are unset, UTC is used (and `doctor` warns you).
- DST transitions are handled automatically via `zoneinfo`.
- You can change tz any time — next build uses the new tz.

## Manual runs

```bash
newsbrief dry-run    # print to stdout
newsbrief run        # build + send once, now
```

These **don't** affect the schedule. The next scheduled build still happens.

## Observability

```bash
newsbrief stats
```

```
Last 7 days:
  builds:  7 ok, 0 failed
  avg build duration:  9m 42s
  p90 build duration:  11m 23s
  delivered on time:   7/7
  items per digest:    ~18
  👍 12  👎 3  🔕 1  📌 4
```

## See also

- [configuration.md](configuration.md#schedule) — `schedule` schema
- [bot-ui.md](bot-ui.md) — schedule settings from the bot
