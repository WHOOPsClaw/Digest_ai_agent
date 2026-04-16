# Contributing

Thanks for helping `newsbrief` — bug reports, PRs, new sources, and preset additions are all welcome.

## Development setup

```bash
git clone https://github.com/newsbrief/newsbrief
cd newsbrief
python -m venv venv
./venv/bin/pip install -e '.[dev]'
```

Python 3.11+ required.

## Running tests

```bash
./venv/bin/pytest                  # full suite
./venv/bin/pytest tests/core       # one directory
./venv/bin/pytest -k discovery     # by keyword
./venv/bin/pytest -x --ff          # stop at first failure, failed-first
```

The suite should stay green (currently 182 tests). Please add tests for any new feature or bug fix.

## Code style

We use:

- **ruff** for linting and formatting
- **mypy** for types
- **pytest** for tests

```bash
./venv/bin/ruff check .
./venv/bin/ruff format .
./venv/bin/mypy newsbrief
```

All three must pass before a PR is mergeable. CI enforces this.

Conventions:

- Type hints on every public function.
- Docstrings on public classes / non-trivial functions (Google style).
- Keep modules small (<500 LoC) and cohesive.
- Prefer pure functions; isolate I/O behind adapters.

## PR guidelines

1. Fork, create a branch from `main`.
2. Small, focused PRs. If in doubt, open an issue first.
3. Include tests.
4. Update docs if behaviour changes.
5. Update `CHANGELOG.md` under `## [Unreleased]`.
6. Pass CI (lint, types, tests).

PR title format: `<area>: <imperative summary>` — e.g. `llm: add support for Mistral preset`.

## How to add...

### A new source adapter

1. Create `newsbrief/sources/<name>.py` subclassing `SourceProvider`.
2. Register with `@register_source("<name>")`.
3. Add a config schema entry in `newsbrief/core/schema.py`.
4. Write tests under `tests/sources/test_<name>.py` with HTTP mocks.
5. Document under `docs/sources.md`.
6. Add one example to `docs/examples/`.

### A new LLM preset

Edit `data/presets.yaml`:

```yaml
- id: coolprovider
  name: "Cool Provider"
  provider: openai                 # OpenAI-compatible shim
  base_url: https://api.coolprovider.com/v1
  default_model: cool-model-7b
  api_key_env: COOL_API_KEY
  buffer_minutes: 10
  free_tier: true
  pricing:
    input_per_1m: 0
    output_per_1m: 0
  links:
    signup: https://coolprovider.com/signup
    docs:   https://docs.coolprovider.com
```

Then:

- Add the env var to the README provider table.
- Add the provider to `docs/llm-providers.md`.
- Test with `newsbrief llm test coolprovider`.
- PR with the preset diff only (one file plus docs).

Use the `llm-preset` issue template if you want to *request* a preset rather than submit one.

### Adding a curated source

Edit `data/known_sources.yaml`:

```yaml
- id: great_blog
  name: "A Great Blog"
  url: https://great-blog.example/feed
  type: rss
  topics: [programming, systems]
  keywords: [rust, linux, performance]
  language: en
  quality: high          # high | medium | low
  freshness: active      # active | intermittent
```

Criteria:

- **Active** — posts at least monthly.
- **Topical** — not a generic news firehose.
- **Language** tagged correctly.
- **Quality** — editorial, not pure aggregator.

If you don't want to submit a PR, open a `source-request` issue — a maintainer will review and add it.

### A bug fix

1. Reproduce the bug in a test (red).
2. Fix the code (green).
3. Ensure no other tests broke.
4. Mention the issue in the PR (`Fixes #123`).

## Filing issues

Use the issue templates in `.github/ISSUE_TEMPLATE/`:

- `bug.md` — something is broken
- `feature.md` — propose a new feature
- `source-request.md` — request a source in the curated DB
- `llm-preset.md` — request a new LLM preset

Include `newsbrief doctor` output for bugs. Redact API keys and tokens before posting.

## Local smoke test

Before submitting a PR, run the full smoke:

```bash
./venv/bin/ruff check .
./venv/bin/ruff format --check .
./venv/bin/mypy newsbrief
./venv/bin/pytest
./venv/bin/newsbrief validate --config docs/examples/ai-researcher.yaml
```

## Release process

Maintainers only:

1. Update `CHANGELOG.md`: move `## [Unreleased]` items under a new version heading.
2. Bump version in `pyproject.toml`.
3. Tag: `git tag vX.Y.Z && git push --tags`.
4. CI builds wheels and Docker image, publishes to PyPI and ghcr.io.

## Code of conduct

Be kind. Assume good faith. No harassment. Report incidents to the maintainers.

## License

By contributing, you agree your contributions will be licensed under MIT.
