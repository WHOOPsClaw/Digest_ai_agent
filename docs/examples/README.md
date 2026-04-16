# Example configs

Drop one of these into your project root as `config.yaml` and run `newsbrief doctor`.

| File                       | Use case                                      | Language | LLM         |
| -------------------------- | --------------------------------------------- | -------- | ----------- |
| `ai-researcher.yaml`       | AI/ML practitioner, deep tech                 | English  | Groq        |
| `russian-news.yaml`        | Russian-speaking, Moscow + world              | Russian  | Gemini      |
| `startup-founder.yaml`     | Tech + HN + founder stories                   | English  | Anthropic   |
| `gaming-enthusiast.yaml`   | AAA + indie + RU gaming scene                 | English  | Groq        |
| `science-fan.yaml`         | Nature, Science, popsci                       | English  | Gemini      |

Remember to set the env vars the preset uses (e.g. `GROQ_API_KEY`, `TELEGRAM_BOT_TOKEN`) and a real `chat_id`.
