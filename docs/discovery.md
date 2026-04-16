# Source Discovery

Describe what you care about — get a ranked list of sources to add to your config.

## How it works

```
   user interests (free text)
             │
             ▼
   ┌─────────────────────────┐
   │   LLM keyword extractor │  "AI research, Rust"
   └───────────┬─────────────┘      ↓
               │             ["llm", "transformers",
               │              "rust", "systems"]
               ▼
   ┌─────────────────────────┐
   │  Curated DB matcher     │  data/known_sources.yaml
   │  (100+ vetted sources)  │  ~85% of results come here
   └───────────┬─────────────┘
               │
               ▼ (gaps remain?)
   ┌─────────────────────────┐
   │  Web search fallback    │  Gemini / SearXNG / Brave
   │  + freshness filter     │  discovers new blogs/channels
   └───────────┬─────────────┘
               │
               ▼
   ┌─────────────────────────┐
   │  Validation             │  fetch sample, check RSS
   │  + dedup                │
   └───────────┬─────────────┘
               ▼
          ranked list →  added to topics
```

## Running

### First run (during setup)

`newsbrief setup` offers to run discovery automatically.

### Standalone

```bash
newsbrief discover
```

Interactive prompt:

```
What are you interested in? (one line, free text)
> Rust systems programming, LLM inference, indie roguelikes

Analysing...
✓ Extracted topics: systems, ai_ml, gaming
✓ Matched 18 sources from curated DB
✓ Web search found 5 additional sources
✓ Validated: 21 work, 2 dead

Suggested topics:
  [1] systems        9 sources
  [2] ai_ml          8 sources
  [3] gaming         4 sources

Apply to config? [Y/n/edit]:
```

### From config

Put interests in `user.profile` and run:

```bash
newsbrief discover --from-config
```

### Targeted

Add sources for one topic without overwriting others:

```bash
newsbrief discover --topic ai_ml --query "LLM agents, RAG, evals"
```

## The curated DB

`data/known_sources.yaml` ships with 100+ vetted sources across ~15 categories:

```yaml
- id: simonwillison_blog
  name: "Simon Willison's Weblog"
  url: https://simonwillison.net/atom/everything/
  type: rss
  topics: [ai_ml, programming]
  keywords: [llm, python, open-source]
  language: en
  quality: high          # high | medium | low
  freshness: active      # active | intermittent
```

## Adding a source to the curated DB

We welcome PRs. Open [`data/known_sources.yaml`](../data/known_sources.yaml) and add an entry following the schema above.

Criteria:

- **Active** — posts at least monthly
- **Topical** — not a generic news firehose unless clearly labelled
- **Language** tagged correctly
- **Quality** — editorial, not pure aggregator

See [CONTRIBUTING.md](../CONTRIBUTING.md#adding-a-curated-source) for the PR workflow. Use the "source request" issue template if you don't want to submit a PR yourself.

## Keyword mapping

The matcher uses a small LLM call to turn free text → canonical topic tags. The canonical tags are:

```
ai_ml, programming, systems, devops, security, crypto, science, space,
gaming, movies, music, business, finance, geopolitics, world_news,
local_ru, local_en, startups, design, productivity, health, climate
```

If a user interest doesn't map cleanly, the extractor falls back to keyword-style matching against the DB's `keywords` field.

## Web search fallback

When the curated DB returns fewer than `min_sources_per_topic` (default 3) for a topic, discovery queries a search backend:

1. Build queries like `"best blogs about <topic>"`, `"<topic> RSS feed"`, `"popular <topic> substack 2025"`.
2. Fetch top 10 results.
3. Try each URL for `/feed`, `/rss`, `/atom.xml`, `/index.xml`.
4. Validate the feed parses and has at least 3 recent items.
5. LLM-rank matches against interests.

Backend is picked per your `llm.providers` config — Gemini with grounding is recommended because it filters stale results.

## Tuning

```yaml
discovery:
  min_sources_per_topic: 3
  max_sources_per_topic: 12
  prefer_language: en              # matches user.language by default
  allow_web_search: true
  freshness_days: 90               # source must have posted in last N days
```

## See also

- [sources.md](sources.md) — manual source config
- [custom-prompts.md](custom-prompts.md) — override the discovery prompt
