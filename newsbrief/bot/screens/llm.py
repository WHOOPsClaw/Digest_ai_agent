"""LLM provider screen."""
from __future__ import annotations

import logging

from newsbrief.bot.menu import MenuScreen, back_button, register_screen
from newsbrief.bot import fsm

logger = logging.getLogger("newsbrief")

# Preset catalog — (id, label, tier, api_key_url)
LLM_PRESETS = [
    ("groq",        "Groq (free)",           "free", "https://console.groq.com/keys"),
    ("together",    "Together (free tier)",  "free", "https://api.together.xyz/settings/api-keys"),
    ("openrouter",  "OpenRouter",            "free", "https://openrouter.ai/keys"),
    ("ollama",      "Ollama (local)",        "free", "https://ollama.com"),
    ("openai",      "OpenAI",                "paid", "https://platform.openai.com/api-keys"),
    ("anthropic",   "Anthropic",             "paid", "https://console.anthropic.com/settings/keys"),
    ("mistral",     "Mistral",               "paid", "https://console.mistral.ai/api-keys"),
    ("gemini",      "Gemini",                "paid", "https://aistudio.google.com/apikey"),
]


def _preset_by_id(preset_id: str):
    for row in LLM_PRESETS:
        if row[0] == preset_id:
            return row
    return None


@register_screen
class LLMScreen(MenuScreen):
    screen_id = "llm"

    def render(self, user_id, config, storage):
        preset = getattr(config.llm, "preset", "groq") if config else "groq"
        model  = getattr(config.llm, "model", None) if config else None
        preset_row = _preset_by_id(preset)
        preset_name = preset_row[1] if preset_row else preset

        text = (
            "🤖 <b>LLM провайдер</b>\n\n"
            f"Сейчас: <b>{preset_name}</b> — {model or 'default'}\n"
            "Статус: ℹ️ проверь кнопкой «Тест»\n"
            "Расход: (данные появятся после первых сборок)"
        )
        keyboard = [
            [{"text": "🔄 Изменить провайдера", "callback_data": "menu:llm:pick"}],
            [{"text": "🔑 Обновить API key",    "callback_data": "menu:llm:rekey"}],
            [{"text": "🧪 Тест",                "callback_data": "menu:llm:test"}],
            [back_button()],
        ]
        return {"text": text, "keyboard": keyboard}

    def handle(self, user_id, action, config, storage, value="", extra=""):
        if action == "pick":
            return "llm_pick"
        if action == "preset":
            # Switch preset
            if config:
                config.llm.preset = value
                try:
                    config.save()
                except Exception as e:
                    logger.warning("[llm] save failed: %s", e)
            # If the provider needs a key, prompt for one
            fsm.set_user_state(user_id, f"awaiting_llm_key:{value}", {"preset": value}, storage)
            return "llm_key"
        if action == "rekey":
            current = getattr(config.llm, "preset", "groq") if config else "groq"
            fsm.set_user_state(user_id, f"awaiting_llm_key:{current}", {"preset": current}, storage)
            return "llm_key"
        if action == "test":
            return "llm_test"
        return None


@register_screen
class LLMPickScreen(MenuScreen):
    screen_id = "llm_pick"

    def render(self, user_id, config, storage):
        current = getattr(config.llm, "preset", "groq") if config else "groq"
        rows = []
        rows.append([{"text": "── Бесплатные ──", "callback_data": "menu:llm_pick:noop"}])
        for pid, label, tier, _url in LLM_PRESETS:
            if tier != "free":
                continue
            marker = " ✅" if pid == current else ""
            rows.append([{"text": label + marker, "callback_data": f"menu:llm:preset:{pid}"}])
        rows.append([{"text": "── Платные ──", "callback_data": "menu:llm_pick:noop"}])
        for pid, label, tier, _url in LLM_PRESETS:
            if tier != "paid":
                continue
            marker = " ✅" if pid == current else ""
            rows.append([{"text": label + marker, "callback_data": f"menu:llm:preset:{pid}"}])
        rows.append([back_button("llm")])
        return {
            "text": "🤖 Выбери провайдера:",
            "keyboard": rows,
        }

    def handle(self, user_id, action, config, storage, value="", extra=""):
        # noop buttons do nothing — keep screen
        return None


@register_screen
class LLMKeyScreen(MenuScreen):
    screen_id = "llm_key"

    def render(self, user_id, config, storage):
        state, ctx = fsm.get_user_state(user_id, storage)
        preset = (ctx or {}).get("preset") or (state.split(":", 1)[1] if state and ":" in state else "")
        row = _preset_by_id(preset) if preset else None
        if row:
            _id, label, _tier, url = row
            text = (
                f"🔑 <b>{label}</b>\n\n"
                f"1. Получи API key: <a href=\"{url}\">{url}</a>\n"
                "2. Пришли его мне следующим сообщением (строкой).\n\n"
                "Ничего никуда не публикуется, ключ остаётся локально в config.yaml."
            )
        else:
            text = "🔑 Пришли API key следующим сообщением."
        return {
            "text": text,
            "keyboard": [[back_button("llm")]],
        }


@register_screen
class LLMTestScreen(MenuScreen):
    screen_id = "llm_test"

    def render(self, user_id, config, storage):
        result_line = "(тест не выполнен)"
        try:
            from newsbrief.llm.router import LLMRouter  # type: ignore
            router = LLMRouter.from_config(config)
            out = router.generate("Say OK")
            result_line = f"Ответ: <code>{str(out)[:200]}</code>"
        except Exception as e:
            result_line = f"⚠️ Ошибка: <code>{e}</code>"
        return {
            "text": "🧪 <b>Тест LLM</b>\n\n" + result_line,
            "keyboard": [[back_button("llm")]],
        }
