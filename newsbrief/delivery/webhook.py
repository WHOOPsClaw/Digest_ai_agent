"""delivery/webhook.py — FastAPI router for Telegram webhook callbacks.

Mount via:
    from newsbrief.delivery.webhook import make_router
    app.include_router(make_router(channel, storage))
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Request

from newsbrief.delivery.telegram import TelegramChannel, parse_callback_data

logger = logging.getLogger("newsbrief")


def make_router(
    channel: TelegramChannel,
    storage=None,
    prefix: str = "/telegram",
    config=None,
) -> APIRouter:
    router = APIRouter(prefix=prefix, tags=["telegram"])

    @router.post("/callback")
    async def telegram_callback(request: Request) -> dict:
        """Receive Telegram update (callback_query) and record feedback."""
        try:
            payload = await request.json()
        except Exception as e:
            logger.warning("[webhook] invalid JSON: %s", e)
            return {"ok": False, "error": "invalid json"}

        cq = payload.get("callback_query")
        if not cq:
            return {"ok": True, "ignored": True}

        cq_id   = cq.get("id", "")
        data    = cq.get("data", "")
        user_id = str(cq.get("from", {}).get("id", ""))
        msg     = cq.get("message") or {}
        chat_id = str(msg.get("chat", {}).get("id", user_id))
        message_id = msg.get("message_id")

        # Settings menu callbacks: menu:screen:action[:value[:extra]]
        if data.startswith("menu:"):
            try:
                from newsbrief.bot.menu import handle_callback
                view = handle_callback(user_id, data, config, storage)
            except Exception as e:
                logger.error("[webhook] menu dispatch failed: %s", e)
                channel.answer_callback_query(cq_id, "Ошибка меню")
                return {"ok": False, "error": "menu dispatch"}
            if message_id:
                channel.edit_message_text(
                    chat_id, int(message_id),
                    view["text"], keyboard=view["keyboard"],
                )
            else:
                channel.send_with_keyboard(chat_id, view["text"], view["keyboard"])
            channel.answer_callback_query(cq_id)
            return {"ok": True, "screen": view.get("screen")}

        parsed = parse_callback_data(data)
        if not parsed:
            channel.answer_callback_query(cq_id, "Неизвестный формат")
            return {"ok": False, "error": "bad callback_data"}

        # Record feedback
        if storage is not None:
            try:
                storage.execute(
                    "INSERT INTO feedback (digest_id, article_url, rating, user_id) "
                    "VALUES (%s, %s, %s, %s)",
                    (
                        parsed["digest_id"],
                        f"idx:{parsed['article_idx']}",
                        parsed["action"],
                        user_id,
                    ),
                )
            except Exception as e:
                logger.error("[webhook] feedback insert failed: %s", e)

        # Acknowledge
        ack_map = {
            "up":   "👍 Спасибо!",
            "down": "👎 Учтено",
            "mute": "🔕 Тема отключена",
            "save": "📌 Сохранено",
        }
        channel.answer_callback_query(cq_id, ack_map.get(parsed["action"], "OK"))
        return {"ok": True, "action": parsed["action"]}

    return router
