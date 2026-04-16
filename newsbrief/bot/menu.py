"""bot/menu.py — main menu and screen dispatcher for Telegram inline UI.

Each ``MenuScreen`` produces ``{text, keyboard}`` dicts and optionally handles
``action`` callbacks. Screens register themselves on import via
``@register_screen``.

Callback data format::

    menu:{screen}:{action}[:{value}[:{extra}…]]

Total length must stay ≤ 64 bytes (Telegram limit).
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional

logger = logging.getLogger("newsbrief")


# ---------------------------------------------------------------------------
# Base screen
# ---------------------------------------------------------------------------

class MenuScreen:
    """Base class for a settings screen."""

    screen_id: str = "base"

    def render(self, user_id: str, config, storage) -> dict:
        """Return {text: str, keyboard: list[list[dict]]}."""
        return {"text": "(empty)", "keyboard": [[back_button()]]}

    def handle(
        self,
        user_id: str,
        action: str,
        config,
        storage,
        value: str = "",
        extra: str = "",
    ) -> Optional[str]:
        """Handle callback action. Return next screen_id or None to stay."""
        if action == "back":
            return "main"
        return None


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

SCREENS: dict[str, MenuScreen] = {}


def register_screen(cls: type) -> type:
    """Decorator: register ``cls`` instance under ``cls.screen_id``."""
    instance = cls()
    SCREENS[instance.screen_id] = instance
    return cls


def get_screen(screen_id: str) -> MenuScreen:
    screen = SCREENS.get(screen_id)
    if screen is None:
        screen = SCREENS.get("main", MenuScreen())
    return screen


# ---------------------------------------------------------------------------
# Helpers for screen authors
# ---------------------------------------------------------------------------

def back_button(to: str = "main", label: str = "⬅️ Назад") -> dict:
    return {"text": label, "callback_data": f"menu:{to}:open"}


def build_callback(screen: str, action: str, value: str = "", extra: str = "") -> str:
    """Build a ``menu:…`` callback_data string (truncated safely to 64 bytes)."""
    parts = ["menu", screen, action]
    if value != "" or extra != "":
        parts.append(value)
    if extra != "":
        parts.append(extra)
    cd = ":".join(parts)
    if len(cd.encode("utf-8")) > 64:
        cd = cd.encode("utf-8")[:64].decode("utf-8", "ignore")
    return cd


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def render_menu_for_user(
    user_id: str,
    config,
    storage,
    screen_id: str = "main",
) -> dict:
    """Render a screen for a user. Returns ``{text, keyboard, screen}``."""
    _ensure_screens_loaded()
    screen = get_screen(screen_id)
    try:
        result = screen.render(str(user_id), config, storage)
    except Exception as e:
        logger.error("[menu] render %s failed: %s", screen_id, e)
        result = {
            "text": f"⚠️ Ошибка рендеринга: {e}",
            "keyboard": [[back_button()]],
        }
    result.setdefault("keyboard", [[back_button()]])
    result["screen"] = screen_id
    return result


def handle_callback(
    user_id: str,
    callback_data: str,
    config,
    storage,
) -> dict:
    """Parse ``menu:…`` callback, dispatch to screen handler, return new view.

    Returns ``{text, keyboard, screen}`` for rendering (typically via
    editMessageText).
    """
    _ensure_screens_loaded()
    parsed = parse_menu_callback(callback_data)
    if parsed is None:
        return {
            "text": "⚠️ Неизвестная команда меню.",
            "keyboard": [[back_button()]],
            "screen": "main",
        }

    screen_id = parsed["screen"]
    action    = parsed["action"]
    value     = parsed["value"]
    extra     = parsed["extra"]

    screen = get_screen(screen_id)

    # "open" is the universal "navigate to this screen" action
    if action == "open":
        return render_menu_for_user(user_id, config, storage, screen_id)

    # Dispatch to screen-specific handler
    try:
        next_screen = screen.handle(
            str(user_id), action, config, storage,
            value=value, extra=extra,
        )
    except Exception as e:
        logger.error("[menu] handle %s:%s failed: %s", screen_id, action, e)
        return {
            "text": f"⚠️ Ошибка: {e}",
            "keyboard": [[back_button()]],
            "screen": screen_id,
        }

    target = next_screen or screen_id
    return render_menu_for_user(user_id, config, storage, target)


def parse_menu_callback(data: str) -> Optional[dict]:
    """Parse ``menu:screen:action[:value[:extra]]`` into a dict.

    Returns ``None`` if data does not start with ``menu:``.
    """
    if not data or not data.startswith("menu:"):
        return None
    parts = data.split(":", 4)
    # ["menu", screen, action, value?, extra?]
    if len(parts) < 3:
        return None
    return {
        "screen": parts[1],
        "action": parts[2],
        "value":  parts[3] if len(parts) > 3 else "",
        "extra":  parts[4] if len(parts) > 4 else "",
    }


# ---------------------------------------------------------------------------
# Lazy import of screen modules to avoid circulars at module load.
# ---------------------------------------------------------------------------

_LOADED = False


def _ensure_screens_loaded() -> None:
    global _LOADED
    if _LOADED:
        return
    # Importing registers screens via decorator
    from newsbrief.bot.screens import (  # noqa: F401
        main as _main,
        schedule as _schedule,
        llm as _llm,
        sources as _sources,
        topic_detail as _topic_detail,
        profile as _profile,
        format as _format,
        notify as _notify,
        stats as _stats,
        pause as _pause,
        diag as _diag,
        reset as _reset,
    )
    _LOADED = True
