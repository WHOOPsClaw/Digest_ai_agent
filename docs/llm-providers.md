# LLM providers

`newsbrief` ships 8 provider presets. All are OpenAI-compatible under the hood (via their native API or a proxy shim).

## Comparison

| Provider   | Free tier            | Input / Output (USD / 1M tok) | Default model              | Typical synth latency | Notes                                      |
| ---------- | -------------------- | ------------------------------ | -------------------------- | --------------------- | ------------------------------------------ |
| Groq       | ✅ generous           | $0 / $0                        | `llama-3.3-70b-versatile`  | ~1s                   | Fastest. RPM cap on free tier.             |
| Gemini     | ✅ generous           | $0.075 / $0.30                 | `gemini-2.0-flash`         | ~2s                   | Best free tier for search/discovery.       |
| Cerebras   | ✅ small              | $0 / $0 (free)                 | `llama3.3-70b`             | <1s                   | Extreme speed. Lower free limits.          |
| Mistral    | ✅ small              | $0.15 / $0.15                  | `mistral-small-latest`     | ~2s                   | EU-hosted. Solid multilingual.             |
| OpenAI     | ❌                    | $0.15 / $0.60 (4o-mini)        | `gpt-4o-mini`              | ~2s                   | Most predictable quality.                  |
| Anthropic  | ❌                    | $0.80 / $4.00 (haiku)          | `claude-3-5-haiku-latest`  | ~2s                   | Best for nuanced "why it matters".         |
| DeepSeek   | ❌                    | $0.14 / $0.28                  | `deepseek-chat`            | ~3s                   | Cheapest for long context.                 |
| OpenRouter | Partial (some free)  | Varies                         | `meta-llama/llama-3.3-70b` | Varies                | One key, many models. Good for mixing.     |

*Prices as of late 2025; always verify on the provider's pricing page.*

## How to choose

### "I just want it to work for free"

Use **Groq**. That's the default.

```yaml
llm:
  preset: groq
```

If you hit Groq's RPM limit (big source list), add Gemini as a fallback:

```yaml
llm:
  preset: groq
  routing:
    filter: gemini       # cheap fast task goes to Gemini
  providers:
    gemini:
      preset: gemini
      api_key_env: GEMINI_API_KEY
```

### "I want the best quality"

Use **Anthropic** for `synthesis`, cheap provider for `filter`:

```yaml
llm:
  preset: anthropic
  model: claude-3-5-haiku-latest
  routing:
    filter: groq
    discovery: gemini
```

Upgrade to `claude-sonnet-4` if budget allows — slower but noticeably better summaries.

### "I want cheapest paid"

Use **DeepSeek** or **gpt-4o-mini**.

### "I self-host"

Point `base_url` at your own endpoint (Ollama, vLLM, LM Studio, LiteLLM):

```yaml
llm:
  provider: openai        # OpenAI-compatible
  base_url: http://localhost:11434/v1
  model: llama3.3:70b
  api_key: ollama         # any non-empty string
```

## Task routing

Three LLM tasks, each routable separately:

| Task        | What it does                                       | Recommended                       |
| ----------- | -------------------------------------------------- | --------------------------------- |
| `filter`    | Rank 200 candidates → top 30                       | Fast, cheap (Groq, Cerebras)      |
| `synthesis` | Write digest cards from top items                  | Quality (Anthropic, Gemini 2.0)   |
| `discovery` | Match interests to known sources / web search      | Web-grounded (Gemini)             |

Example mixed config:

```yaml
llm:
  preset: groq                    # default for anything unrouted
  routing:
    synthesis: anthropic
    discovery: gemini
  providers:
    anthropic:
      preset: anthropic
      api_key_env: ANTHROPIC_API_KEY
    gemini:
      preset: gemini
      api_key_env: GEMINI_API_KEY
```

## Testing

```bash
newsbrief llm list               # show configured providers
newsbrief llm test               # ping default
newsbrief llm test anthropic     # ping a named provider
newsbrief llm switch gemini      # set gemini as default
```

## Cost estimate

A typical daily digest with 5 topics, 15 sources each, 5 items per topic uses roughly:

- **Filter**: ~50k input, ~5k output tokens
- **Synthesis**: ~30k input, ~3k output tokens

Monthly at 30 digests:

- Groq: **$0**
- Gemini 2.0 Flash: **~$0.07**
- gpt-4o-mini: **~$0.14**
- Claude 3.5 Haiku: **~$0.70**
- Sonnet 4: **~$5**

Add discovery runs (~1 per month): negligible.

## See also

- [custom-prompts.md](custom-prompts.md) — tune the prompts per provider
- [configuration.md](configuration.md#llm) — full `llm` schema
