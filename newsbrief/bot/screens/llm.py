"""LLM provider dashboard — multi-provider management."""
from __future__ import annotations

import logging

from newsbrief.bot.menu import MenuScreen, back_button, register_screen
from newsbrief.bot import fsm
from newsbrief.llm import manager as llm_manager

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
    ("custom",      "Custom (OpenAI-compatible)", "free", ""),
]


def _preset_by_id(preset_id: str):
    for row in LLM_PRESETS:
        if row[0] == preset_id:
            return row
    return None


def _status_emoji(status: str) -> str:
    return {"ok": "🟢", "missing_key": "🟡", "error": "🔴"}.get(status, "⚪️")


@register_screen
class LLMScreen(MenuScreen):
    screen_id = "llm"

    def render(self, user_id, config, storage):
        text_lines = ["🤖 <b>LLM провайдер</b>", ""]

        if config is None:
            return {"text": "🤖 LLM: конфиг недоступен.", "keyboard": [[back_button()]]}

        providers = llm_manager.list_providers(config)
        if providers:
            active = next((p for p in providers if p["active"]), None)
            if active:
                text_lines.append(
                    f"Активный: {_status_emoji(active['status'])} "
                    f"<b>{active['display_name']}</b> — {active['model'] or 'default'}"
                )
            else:
                text_lines.append("Активный: (не выбран)")
            text_lines.append("")
            text_lines.append("Подключённые провайдеры:")
            for p in providers:
                marker = " (активный)" if p["active"] else ""
                text_lines.append(
                    f"• {_status_emoji(p['status'])} {p['display_name']}"
                    + (f" — {p['model']}" if p["model"] else "")
                    + marker
                )
        else:
            # Fall back to legacy single-provider view.
            preset = getattr(config.llm, "preset", "groq") or "groq"
            model  = getattr(config.llm, "model", None)
            row = _preset_by_id(preset)
            label = row[1] if row else preset
            text_lines.append(f"Сейчас: <b>{label}</b> — {model or 'default'}")
            text_lines.append("(провайдеры ещё не настроены — добавь первый)")

        keyboard = [
            [{"text": "🔄 Переключить активный",  "callback_data": "menu:llm_switch:open"}],
            [{"text": "➕ Добавить провайдер",    "callback_data": "menu:llm_add:open"}],
            [{"text": "🗑 Удалить провайдер",     "callback_data": "menu:llm_remove:open"}],
            [{"text": "🧪 Протестировать все",    "callback_data": "menu:llm_test_all:open"}],
            [back_button()],
        ]
        return {"text": "\n".join(text_lines), "keyboard": keyboard}

    def handle(self, user_id, action, config, storage, value="", extra=""):
        # Backward-compat: legacy callbacks still work.
        if action == "pick":
            return "llm_pick"
        if action == "preset":
            if config:
                config.llm.preset = value
                try:
                    config.save()
                except Exception as e:  # noqa: BLE001
                    logger.warning("[llm] save failed: %s", e)
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
    """Legacy preset picker — retained for backward compat."""
    screen_id = "llm_pick"

    def render(self, user_id, config, storage):
        current = getattr(config.llm, "preset", "groq") if config else "groq"
        rows = []
        rows.append([{"text": "── Бесплатные ──", "callback_data": "menu:llm_pick:noop"}])
        for pid, label, tier, _url in LLM_PRESETS:
            if tier != "free" or pid == "custom":
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
        return {"text": "🤖 Выбери провайдера:", "keyboard": rows}

    def handle(self, user_id, action, config, storage, value="", extra=""):
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
                "Ничего никуда не публикуется, ключ хранится локально."
            )
        else:
            text = "🔑 Пришли API key следующим сообщением."
        return {"text": text, "keyboard": [[back_button("llm")]]}


@register_screen
class LLMTestScreen(MenuScreen):
    screen_id = "llm_test"

    def render(self, user_id, config, storage):
        result_line = "(тест не выполнен)"
        try:
            from newsbrief.llm.router import LLMRouter
            router = LLMRouter(config)
            out = router.test()
            if isinstance(out, dict) and out.get("ok"):
                result_line = (
                    f"✅ OK — model={out.get('model')} "
                    f"latency={out.get('latency_ms')}ms"
                )
            else:
                result_line = f"⚠️ {out}"
        except Exception as e:  # noqa: BLE001
            result_line = f"⚠️ Ошибка: <code>{e}</code>"
        return {
            "text": "🧪 <b>Тест LLM</b>\n\n" + result_line,
            "keyboard": [[back_button("llm")]],
        }
