"""Interactive setup wizard — 5 questions from zero to working digest.

Flow:
  1. Telegram bot token (link to @BotFather)
  2. Telegram chat_id (auto-detect via polling)
  3. LLM provider (preset selection + API key)
  4. Interests (free text → Source Discovery)
  5. Delivery time (presets or custom)
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

try:
    import questionary
except ImportError:
    questionary = None

from newsbrief.config import NewsbriefConfig

logger = logging.getLogger("newsbrief")

BANNER = """
╔══════════════════════════════════════╗
║       newsbrief — setup wizard       ║
║   От 0 до первого дайджеста за 5 мин ║
╚══════════════════════════════════════╝
"""


def run_setup() -> int:
    """Main entrypoint for `newsbrief setup`."""
    print(BANNER)

    if questionary is None:
        print("ERROR: questionary not installed. Run: pip install questionary")
        return 1

    cfg = NewsbriefConfig.load()  # empty default if first run

    # Step 1: Telegram token
    token = _ask_telegram_token(cfg.delivery.telegram.bot_token)
    if not token:
        return 1

    # Step 2: chat_id
    chat_id = _ask_chat_id(cfg.delivery.telegram.chat_id, token)
    if not chat_id:
        return 1

    # Step 3: LLM preset + key
    llm_cfg = _ask_llm()
    if not llm_cfg:
        return 1

    # Step 4: interests
    interests = _ask_interests(cfg.user.profile)

    # Step 5: delivery time
    send_at = _ask_delivery_time(cfg.schedule.send_at)

    # Build config
    cfg.delivery.telegram.bot_token = token
    cfg.delivery.telegram.chat_id = chat_id
    cfg.llm = llm_cfg
    cfg.user.profile = interests
    cfg.schedule.send_at = send_at

    # Save
    cfg.save()
    _save_env({"TELEGRAM_BOT_TOKEN": token, "TELEGRAM_CHAT_ID": chat_id,
               "LLM_API_KEY": llm_cfg.api_key or ""})

    print("\n✅ Config saved to config.yaml")
    print("✅ Secrets saved to .env")

    # Run source discovery if interests given
    if interests:
        print("\n🔍 Запускаю поиск источников по твоим интересам...")
        try:
            from newsbrief.discovery.wizard import run_discovery_wizard
            from newsbrief.llm.router import LLMRouter
            router = LLMRouter(cfg)
            topics = run_discovery_wizard(cfg, router)
            if topics:
                from newsbrief.config import TopicConfig
                cfg.topics = [TopicConfig.model_validate(t) for t in topics]
                cfg.save()
                print(f"✅ Подобрано {len(topics)} тем, сохранено в config.yaml")
        except Exception as e:
            logger.warning("discovery skipped: %s", e)
            print(f"⚠️  Discovery не запустился: {e}")

    # Run doctor
    print("\n🔧 Проверяю подключения...")
    from newsbrief.core.doctor import run_doctor
    run_doctor()

    print("\n✅ Готово! Запусти: docker compose up -d")
    print("   Первый дайджест придёт завтра в", send_at)
    return 0


def _ask_telegram_token(current: str = "") -> str:
    if current:
        change = questionary.confirm(
            f"Telegram token уже есть (...{current[-6:]}). Изменить?", default=False,
        ).ask()
        if not change:
            return current

    print("\n━━━ 1. Telegram Bot Token ━━━")
    print("Получить у @BotFather в Telegram:")
    print("  1. Напиши /newbot")
    print("  2. Придумай имя")
    print("  3. Скопируй token (формат 1234567890:ABC...)")

    token = questionary.password("Token:").ask()
    if not token or ":" not in token:
        print("❌ Неверный формат токена")
        return ""
    return token


def _ask_chat_id(current: str, token: str) -> str:
    if current:
        change = questionary.confirm(
            f"chat_id уже есть ({current}). Изменить?", default=False,
        ).ask()
        if not change:
            return current

    print("\n━━━ 2. Твой chat_id ━━━")
    print("Сейчас определю автоматически.")
    print(f"1. Открой своего бота в Telegram")
    print(f"2. Напиши ему /start (или любое сообщение)")

    use_auto = questionary.confirm("Готов? Ждать сообщения 60 секунд?", default=True).ask()
    if use_auto:
        chat_id = _poll_chat_id(token)
        if chat_id:
            print(f"✅ chat_id получен: {chat_id}")
            return chat_id
        print("⚠️ Сообщение не пришло, введи chat_id вручную")

    chat_id = questionary.text("chat_id (число):").ask()
    return chat_id or ""


def _poll_chat_id(token: str, timeout: int = 60) -> str:
    """Poll getUpdates for 60 sec to detect chat_id."""
    import time
    import httpx

    url = f"https://api.telegram.org/bot{token}/getUpdates"
    deadline = time.time() + timeout
    offset = 0
    while time.time() < deadline:
        try:
            resp = httpx.get(url, params={"offset": offset, "timeout": 5}, timeout=10)
            data = resp.json()
            for upd in data.get("result", []):
                msg = upd.get("message") or upd.get("channel_post")
                if msg and msg.get("chat"):
                    return str(msg["chat"]["id"])
                offset = max(offset, upd.get("update_id", 0) + 1)
        except Exception as e:
            logger.warning("poll error: %s", e)
        time.sleep(1)
    return ""


def _ask_llm():
    """Ask LLM preset and API key. Returns LLMConfig or None."""
    from newsbrief.config import LLMConfig

    print("\n━━━ 3. LLM провайдер ━━━")
    choice = questionary.select(
        "Какой LLM использовать?",
        choices=[
            "Groq (БЕСПЛАТНО, Llama 3.3 70B) ⭐ рекомендую",
            "Gemini (БЕСПЛАТНО, Google)",
            "Cerebras (БЕСПЛАТНО, супер-быстрый)",
            "Mistral (БЕСПЛАТНО)",
            "OpenAI (платный, GPT-4o mini)",
            "Anthropic (платный, Claude Haiku)",
            "DeepSeek (самый дешёвый платный)",
            "OpenRouter (100+ моделей)",
            "Свой (base_url + model)",
        ],
    ).ask()

    if not choice:
        return None

    preset_map = {
        "Groq": "groq",
        "Gemini": "gemini",
        "Cerebras": "cerebras",
        "Mistral": "mistral",
        "OpenAI": "openai",
        "Anthropic": "anthropic",
        "DeepSeek": "deepseek",
        "OpenRouter": "openrouter",
    }
    preset = None
    for key, val in preset_map.items():
        if choice.startswith(key):
            preset = val
            break

    if preset is None:
        # custom
        base_url = questionary.text("base_url:").ask()
        model = questionary.text("model:").ask()
        api_key = questionary.password("API key:").ask()
        return LLMConfig(
            preset=None, provider="openai_compatible",
            base_url=base_url, model=model, api_key=api_key,
        )

    # Preset path — show where to get key
    url_map = {
        "groq": "https://console.groq.com/keys",
        "gemini": "https://aistudio.google.com/apikey",
        "cerebras": "https://cloud.cerebras.ai",
        "mistral": "https://console.mistral.ai/api-keys",
        "openai": "https://platform.openai.com/api-keys",
        "anthropic": "https://console.anthropic.com/settings/keys",
        "deepseek": "https://platform.deepseek.com/api_keys",
        "openrouter": "https://openrouter.ai/keys",
    }
    print(f"\n🔑 Получи API key тут: {url_map[preset]}")
    api_key = questionary.password("Вставь API key:").ask()
    return LLMConfig(preset=preset, api_key=api_key)


def _ask_interests(current: str = "") -> str:
    print("\n━━━ 4. Интересы ━━━")
    print("Опиши что тебе интересно. AI подберёт источники и будет ранжировать новости.")
    print("Пример: 'AI coding agents, Tesla автопилоты, российская политика, AAA игры'")

    if current:
        print(f"\nТекущие: {current[:150]}...")
        change = questionary.confirm("Изменить?", default=False).ask()
        if not change:
            return current

    text = questionary.text("Интересы:", multiline=True).ask()
    return text or ""


def _ask_delivery_time(current: str = "09:00") -> str:
    print("\n━━━ 5. Время доставки ━━━")
    choice = questionary.select(
        "Во сколько получать дайджест?",
        choices=[
            "07:00 — рано утром",
            "08:00 — перед работой",
            "09:00 — с утренним кофе",
            "10:00 — после просыпания ⭐",
            "12:00 — в обед",
            "18:00 — после работы",
            "20:00 — вечером",
            "Custom (HH:MM)",
        ],
        default=f"{current} — с утренним кофе" if current == "09:00" else None,
    ).ask()

    if not choice:
        return current

    if choice.startswith("Custom"):
        t = questionary.text("Время (HH:MM):").ask()
        return t or "09:00"

    return choice.split(" —")[0]


def _save_env(env: dict) -> None:
    """Write .env file (overwrite)."""
    lines = ["# newsbrief — auto-generated by setup wizard"]
    for k, v in env.items():
        lines.append(f"{k}={v}")
    Path(".env").write_text("\n".join(lines) + "\n")
