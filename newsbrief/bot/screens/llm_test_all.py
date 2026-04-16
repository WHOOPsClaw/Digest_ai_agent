"""Test all configured LLM providers, show results table."""
from __future__ import annotations

import logging

from newsbrief.bot.menu import MenuScreen, back_button, register_screen
from newsbrief.llm import manager as llm_manager

logger = logging.getLogger("newsbrief")


@register_screen
class LLMTestAllScreen(MenuScreen):
    screen_id = "llm_test_all"

    def render(self, user_id, config, storage):
        if config is None:
            return {"text": "⚠️ Конфиг недоступен.", "keyboard": [[back_button("llm")]]}

        providers = llm_manager.list_providers(config)
        if not providers:
            return {
                "text": "Нет провайдеров для проверки.",
                "keyboard": [[back_button("llm")]],
            }

        lines = ["🧪 <b>Тест всех провайдеров</b>", ""]
        for p in providers:
            try:
                result = llm_manager.test_provider(config, p["id"])
            except Exception as e:  # noqa: BLE001
                result = {"ok": False, "latency_ms": 0, "error": str(e)}
            if result.get("ok"):
                lines.append(
                    f"🟢 {p['display_name']} — {result.get('latency_ms', 0)}ms"
                )
            else:
                err = result.get("error") or "fail"
                lines.append(f"🔴 {p['display_name']} — {err}")

        return {"text": "\n".join(lines), "keyboard": [[back_button("llm")]]}
