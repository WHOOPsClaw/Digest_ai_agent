---
name: Source request
about: Request a source be added to the curated DB
title: "[source] "
labels: source-request
assignees: ''
---

<!-- Use this if you want a source added to data/known_sources.yaml but don't want to open a PR yourself. For PRs see CONTRIBUTING.md. -->

## Source details

- **Name**:
- **URL** (feed or page):
- **Type**: [ ] RSS/Atom  [ ] Telegram  [ ] Reddit  [ ] HackerNews  [ ] YouTube
- **Language**:
- **Topics / tags** (e.g. `ai_ml`, `systems`, `gaming`):
- **Keywords** (3–8 short phrases):

## Why this source

<!-- Why should it be in the curated DB? What does it cover well? -->

## Criteria check

- [ ] Active (posts at least monthly)
- [ ] Topical (not a generic news firehose)
- [ ] Editorial (not a pure aggregator)
- [ ] I've verified the feed URL works (`curl` or browser)

## Proposed YAML entry

```yaml
- id: short_id_here
  name: ""
  url: ""
  type: rss
  topics: []
  keywords: []
  language: en
  quality: high
  freshness: active
```
