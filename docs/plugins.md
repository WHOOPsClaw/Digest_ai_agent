# Plugins

Extend `newsbrief` with custom sources, LLM providers, and delivery channels.

Plugins are regular Python modules loaded from `~/.newsbrief/plugins/` (or `$NEWSBRIEF_PLUGIN_DIR`). A plugin is a `.py` file that registers its classes at import time.

## Plugin types

| Type              | Base class        | Registry                        |
| ----------------- | ----------------- | ------------------------------- |
| Source            | `SourceProvider`  | `newsbrief.sources.registry`    |
| LLM               | `LLMProvider`     | `newsbrief.llm.registry`        |
| Delivery channel  | `DeliveryChannel` | `newsbrief.delivery.registry`   |

---

## Custom source

Say you want a "Mastodon user feed" source.

`~/.newsbrief/plugins/mastodon_source.py`:

```python
from datetime import datetime
from newsbrief.sources.base import SourceProvider, Item, register_source
import httpx


@register_source("mastodon")
class MastodonSource(SourceProvider):
    """Fetch a Mastodon user's public posts."""

    def __init__(self, config: dict):
        self.acct = config["acct"]              # e.g. "simon@fedi.simonwillison.net"
        self.limit = config.get("limit", 20)

    def fetch(self) -> list[Item]:
        user, host = self.acct.split("@")
        # Resolve user id
        r = httpx.get(f"https://{host}/api/v1/accounts/lookup",
                      params={"acct": user}, timeout=10)
        r.raise_for_status()
        uid = r.json()["id"]

        # Fetch statuses
        r = httpx.get(f"https://{host}/api/v1/accounts/{uid}/statuses",
                      params={"limit": self.limit, "exclude_replies": True},
                      timeout=10)
        r.raise_for_status()

        items = []
        for post in r.json():
            items.append(Item(
                id=post["uri"],
                title=post["content"][:140],
                url=post["url"],
                body=post["content"],
                published=datetime.fromisoformat(post["created_at"]),
                source=f"mastodon:{self.acct}",
            ))
        return items
```

Use in `config.yaml`:

```yaml
sources:
  mastodon:
    - acct: "simon@fedi.simonwillison.net"
    - acct: "hynek@mastodon.social"
      limit: 10
```

---

## Custom LLM provider

Integrate a proprietary or self-hosted endpoint that isn't OpenAI-compatible.

`~/.newsbrief/plugins/llama_cpp_provider.py`:

```python
from newsbrief.llm.base import LLMProvider, ChatMessage, register_llm
import httpx


@register_llm("llama_cpp")
class LlamaCppProvider(LLMProvider):
    """Talk to a llama.cpp server's /completion endpoint."""

    def __init__(self, config: dict):
        self.base_url = config.get("base_url", "http://localhost:8080")
        self.temperature = config.get("temperature", 0.3)

    def chat(self, messages: list[ChatMessage], **kw) -> str:
        prompt = "\n".join(f"{m.role}: {m.content}" for m in messages)
        r = httpx.post(
            f"{self.base_url}/completion",
            json={"prompt": prompt, "temperature": self.temperature,
                  "n_predict": kw.get("max_tokens", 1024)},
            timeout=120,
        )
        r.raise_for_status()
        return r.json()["content"]
```

```yaml
llm:
  provider: llama_cpp
  base_url: http://localhost:8080
```

---

## Custom delivery channel

Deliver to Discord, Matrix, email — anywhere.

`~/.newsbrief/plugins/discord_delivery.py`:

```python
from newsbrief.delivery.base import DeliveryChannel, Digest, register_delivery
import httpx


@register_delivery("discord")
class DiscordWebhook(DeliveryChannel):
    """Post digests to a Discord channel via webhook."""

    def __init__(self, config: dict):
        self.webhook_url = config["webhook_url"]

    def send(self, digest: Digest) -> None:
        for block in digest.blocks:
            payload = {
                "username": "newsbrief",
                "embeds": [{
                    "title": f"{block.emoji} {block.title}",
                    "description": block.body[:4000],
                    "color": 0x5865F2,
                }],
            }
            r = httpx.post(self.webhook_url, json=payload, timeout=15)
            r.raise_for_status()
```

```yaml
delivery:
  discord:
    webhook_url: https://discord.com/api/webhooks/xxx/yyy
```

You can enable multiple delivery channels — all get the same digest.

---

## Loading

At startup, `newsbrief` scans:

1. `$NEWSBRIEF_PLUGIN_DIR` (if set)
2. `~/.newsbrief/plugins/`
3. `./plugins/` (next to `config.yaml`)

Each `.py` file is imported once. Decorators (`@register_source`, etc.) register the class in the appropriate registry.

Failures are logged but don't crash the daemon:

```
WARN  plugin mastodon_source.py: ImportError: No module named 'httpx'
```

Install plugin dependencies into the same env as `newsbrief`.

## Testing a plugin

```bash
newsbrief validate               # checks plugins load without error
newsbrief sources --list         # your new type should appear
newsbrief dry-run                # end-to-end test
```

For unit tests, import the plugin and instantiate directly:

```python
from plugins.mastodon_source import MastodonSource

def test_fetch():
    src = MastodonSource({"acct": "simon@fedi.simonwillison.net", "limit": 3})
    items = src.fetch()
    assert len(items) <= 3
    assert all(i.url for i in items)
```

## Packaging

For broader distribution, package as a pip-installable module with entry points:

```toml
# pyproject.toml
[project.entry-points."newsbrief.sources"]
mastodon = "my_plugin.mastodon:MastodonSource"
```

`newsbrief` will pick up any entry point under `newsbrief.sources`, `newsbrief.llm`, `newsbrief.delivery`.

## See also

- [sources.md](sources.md) — built-in source types
- [llm-providers.md](llm-providers.md) — built-in providers
- [CONTRIBUTING.md](../CONTRIBUTING.md) — if you want your plugin upstreamed
