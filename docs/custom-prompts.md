# Custom prompts

You can override every built-in prompt via `config.yaml`.

```yaml
prompts:
  synthesis: |
    You are a news analyst writing for a senior engineer.
    Prefer concrete numbers over adjectives. Drop marketing fluff.
    End each card with one sharp "why it matters" sentence.

  filter: |
    Drop anything that is:
      - a press release with no new data
      - a rehashed summary without new sources
      - celebrity gossip
    Keep anything with primary sources or fresh benchmarks.

  discovery: |
    Prefer independent blogs and newsletters over corporate newsrooms.
    Exclude feeds that repost content from elsewhere.
```

## Overridable prompts

| Key                 | Task                                      | Called per       |
| ------------------- | ----------------------------------------- | ---------------- |
| `synthesis`         | Write the digest cards                    | Digest build     |
| `synthesis_card`    | Format one card (fallback to `synthesis`) | Per item         |
| `filter`            | Rank candidate items                      | Digest build     |
| `why_it_matters`    | Write the blockquote line                 | Per item         |
| `discovery`         | Match interests → sources                 | `discover` cmd   |
| `discovery_keywords`| Extract canonical topic tags              | `discover` cmd   |
| `translation`       | Translate source → `user.language`        | Per item (opt)   |
| `dedup`             | Decide if two items are duplicates        | Filter stage     |

## Template variables

Prompts are Jinja2 templates. Variables available in most prompts:

| Variable             | Type        | Example                                    |
| -------------------- | ----------- | ------------------------------------------ |
| `{{ user.name }}`    | string      | `Alex`                                     |
| `{{ user.language }}`| string      | `en`                                       |
| `{{ user.profile }}` | string      | `"AI research, Rust..."`                   |
| `{{ topic.id }}`     | string      | `ai_ml`                                    |
| `{{ topic.name }}`   | string      | `AI & ML`                                  |
| `{{ items }}`        | list[Item]  | candidate items with `title`, `url`, ...   |
| `{{ now }}`          | datetime    | current time in user's tz                  |
| `{{ language }}`     | string      | target output language                     |

Inside `synthesis` the `items` list is pre-filtered and ranked.

## Example: Russian-language personal voice

```yaml
user:
  language: ru
  name: Илья

prompts:
  synthesis: |
    Ты пишешь дайджест для занятого инженера. Обращайся на «ты».
    Никакого канцелярита. Короткие фразы, конкретные числа.
    В конце каждой карточки одна строка «зачем это читать».

  filter: |
    Выбрасывай пресс-релизы, желтуху, репосты без новой информации.
    Приоритет — первоисточники, новые бенчмарки, код.
```

## Example: tune per-topic voice

Per-topic overrides live under the topic:

```yaml
topics:
  - id: gaming
    name: "Games"
    prompts:
      synthesis: |
        Write with playful energy. It's OK to be opinionated about games.
        Tag each card with [indie] / [AAA] / [mobile].
```

Topic-level prompt wins over top-level `prompts`.

## Testing a prompt

```bash
newsbrief dry-run --topic ai_ml
```

This builds the digest for one topic and prints the final Telegram markup to stdout. Fastest iteration loop.

Combine with `--model` to try a different LLM without changing config:

```bash
newsbrief dry-run --topic ai_ml --model anthropic:claude-3-5-haiku-latest
```

## Tips

- Keep prompts short — every token costs latency and money.
- Prefer **rules** over **examples** when possible (fewer tokens).
- Use the `language` variable so your prompt adapts to `user.language` automatically.
- Test with `dry-run` before deploying — a bad prompt can silently drop items.
- For multilingual users: write the meta-instruction in English, put output-language demands inline (e.g. "write the final output in `{{ language }}`").

## See also

- [llm-providers.md](llm-providers.md) — each provider responds slightly differently
- [configuration.md](configuration.md#prompts) — full schema
