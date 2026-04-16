# Sources

`newsbrief` supports 6 source types. You can mix any number per topic.

Every source has an optional `role`:

- `source` (default) — primary content, items are candidates for inclusion
- `signal` — used to score importance ("if HN mentions it, it's worth attention")
- `analysis` — used only to enrich "why it matters"

## RSS / Atom

Any RSS or Atom feed URL.

```yaml
sources:
  rss:
    - https://simonwillison.net/atom/everything/
    - https://jack-clark.net/feed/
    - url: https://feeds.bbci.co.uk/news/world/rss.xml
      role: source
      weight: 0.8
      name: "BBC World"
```

### Finding RSS feeds

- [RSS.app](https://rss.app) — generate a feed from any website
- [FetchRSS](https://fetchrss.com) — extract a feed from a page
- Look for the 📡 icon in the browser address bar
- Try suffixes: `/feed`, `/rss`, `/atom.xml`, `/index.xml`, `/feed.xml`
- For Substack: `https://NAME.substack.com/feed`
- For WordPress: `https://SITE/feed/`
- For Medium user: `https://medium.com/feed/@USERNAME`

## Telegram

Public channels only (no login required).

```yaml
sources:
  telegram:
    - neuraldvig
    - varlamov_news
    - username: denissexy
      role: signal
```

### Finding channels

- [tgstat.com](https://tgstat.com) — directory with stats
- Open the channel in Telegram, copy the `@username`
- Channel must be **public** (has a `t.me/name` link)

Private channels require a userbot and are out of scope for v0.1.

## Reddit

Subreddits fetched via the public JSON endpoint (`/r/NAME/.json`).

```yaml
sources:
  reddit:
    - MachineLearning
    - LocalLLaMA
    - name: rust
      sort: top            # hot (default) | top | new | rising
      window: day          # only with sort=top: hour, day, week, month, year, all
      min_score: 50
```

## HackerNews

```yaml
sources:
  hackernews:
    - top            # top stories
    - new            # new stories
    - best           # best stories
    - name: ask
      min_score: 100
      max_age_hours: 48
```

Filters:

- `min_score` — skip under this karma
- `min_comments` — skip under this comment count
- `max_age_hours` — skip older than N hours

## YouTube

Channels via their RSS endpoint. Transcripts are optional (via `youtube-transcript-api`).

```yaml
sources:
  youtube:
    - UCxxxxxxxxxxxxxxxxxxx              # channel ID
    - channel_id: UCxxxxxxxxxxxxxxxxxxx
      transcripts: true
      min_duration_minutes: 5
```

### Finding a YouTube channel ID

1. Open the channel page.
2. View source, search for `channelId`.
3. Or paste the URL into [commentpicker.com/youtube-channel-id.php](https://commentpicker.com/youtube-channel-id.php).

## Search

Query-based discovery via a search backend.

```yaml
sources:
  search:
    - "open-weights LLM release this week"
    - query: "indie game release roguelike"
      backend: searxng
      max_results: 5
      freshness: week      # day | week | month
```

Backends:

- `searxng` — self-hosted ([searxng.org](https://docs.searxng.org)). Configure `SEARXNG_BASE_URL` env var.
- `brave` — [brave.com/search/api](https://brave.com/search/api/). `BRAVE_API_KEY` env var.
- `ddg` — DuckDuckGo via `duckduckgo-search`. No key. Rate-limited.

## Mixing roles

A realistic `sources` block:

```yaml
sources:
  rss:
    - https://simonwillison.net/atom/everything/   # primary
    - url: https://news.ycombinator.com/rss
      role: signal                                 # signal only
  telegram: [ai_newz]
  hackernews: [top]
  search:
    - query: "new LLM paper arxiv"
      role: analysis                               # for "why it matters"
```

## Checking sources

```bash
newsbrief sources --check                # all sources
newsbrief sources --topic ai --check     # one topic
newsbrief sources add rss https://...    # add a feed
newsbrief sources rm rss 3               # remove by index
```

Dead sources (3 consecutive failures) are auto-disabled and reported by `doctor`.

## See also

- [discovery.md](discovery.md) — auto-find sources by interests
- [configuration.md](configuration.md#topics) — full topic schema
