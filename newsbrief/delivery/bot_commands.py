"""delivery/bot_commands.py — Telegram bot command handlers.

Simple long-polling loop using httpx (no python-telegram-bot dep).

Commands:
  /start    — welcome + setup hint
  /digest   — manual trigger
  /stats    — weekly stats
  /pause    — pause deliveries
  /resume   — resume deliveries
  /menu     — (sprint 6 placeholder)
  /schedule — change delivery time
"""
from __future__ import annotations

import logging
import time
from typing import Callable, Optional

import httpx

from newsbrief.delivery.telegram import TELEGRAM_API_BASE, TELEGRAM_TIMEOUT, TelegramChannel

logger = logging.getLogger("newsbrief")

POLL_TIMEOUT_SEC  = 30


class BotCommandHandler:
    def __init__(
        self,
        channel: TelegramChannel,
        storage=None,
        config=None,
        on_digest: Optional[Callable] = None,
        on_stats:  Optional[Callable] = None,
        on_schedule: Optional[Callable] = None,
    ):
        self.channel    = channel
        self.storage    = storage
        self.config     = config
        self.on_digest   = on_digest
        self.on_stats    = on_stats
        self.on_schedule = on_schedule

        self._last_update_id: int = 0
        self._running:        bool = False

    # --- commands ------------------------------------------------------

    def handle_start(self, chat_id: str) -> str:
        return (
            "👋 <b>Добро пожаловать в newsbrief!</b>\n\n"
            "Это self-hosted AI-дайджест новостей.\n\n"
            "Команды:\n"
            "• /digest — получить дайджест сейчас\n"
            "• /schedule — изменить время доставки\n"
            "• /stats — недельная статистика\n"
            "• /pause /resume — пауза/возобновление\n\n"
            "Запустите <code>newsbrief setup</code> в терминале для настройки."
        )

    def handle_digest(self, chat_id: str) -> str:
        if not self.on_digest:
            return "⚠️ Обработчик дайджеста не настроен."
        try:
            self.on_digest(chat_id)
            return "🚀 Запускаю дайджест…"
        except Exception as e:
            logger.error("[bot] digest failed: %s", e)
            return f"❌ Ошибка: {e}"

    def handle_stats(self, chat_id: str) -> str:
        if self.on_stats:
            try:
                return self.on_stats()
            except Exception as e:
                return f"❌ Ошибка: {e}"
        if not self.storage:
            return "Статистика недоступна."
        try:
            rows = self.storage.fetchall(
                "SELECT COUNT(*) AS n FROM digests "
                "WHERE created_at >= date('now', '-7 days')"
            )
            n = rows[0].get("n", 0) if rows else 0
            return f"📊 Дайджестов за 7 дней: <b>{n}</b>"
        except Exception as e:
            return f"❌ Ошибка: {e}"

    def handle_pause(self, chat_id: str) -> str:
        if self.storage:
            self.storage.execute(
                "INSERT OR REPLACE INTO bot_state (user_id, current_state, updated_at) "
                "VALUES (%s, %s, CURRENT_TIMESTAMP)",
                (str(chat_id), "paused"),
            )
        return "⏸ Доставка приостановлена. /resume для возобновления."

    def handle_resume(self, chat_id: str) -> str:
        if self.storage:
            self.storage.execute(
                "INSERT OR REPLACE INTO bot_state (user_id, current_state, updated_at) "
                "VALUES (%s, %s, CURRENT_TIMESTAMP)",
                (str(chat_id), "active"),
            )
        return "▶️ Доставка возобновлена."

    def handle_menu(self, chat_id: str) -> Optional[str]:
        """Render the main settings menu and send it with an inline keyboard.

        Returns None because we send directly (keyboard attached) rather than
        letting the dispatcher fall back to a plain text reply.
        """
        try:
            from newsbrief.bot.menu import render_menu_for_user
            view = render_menu_for_user(str(chat_id), self.config, self.storage, "main")
        except Exception as e:
            logger.error("[bot] /menu render failed: %s", e)
            return f"⚠️ Ошибка меню: {e}"
        try:
            self.channel.send_with_keyboard(str(chat_id), view["text"], view["keyboard"])
        except Exception as e:
            logger.error("[bot] /menu send failed: %s", e)
            return "⚠️ Не удалось отправить меню."
        return None

    # --- FSM text-input handling --------------------------------------

    def handle_text_input(self, chat_id: str, text: str) -> Optional[str]:
        """If user is in an FSM awaiting state, consume the text.

        Returns a reply string (or None if not awaiting).
        """
        try:
            from newsbrief.bot import fsm
            state, ctx = fsm.get_user_state(str(chat_id), self.storage)
        except Exception as e:
            logger.warning("[bot] fsm lookup failed: %s", e)
            return None
        if not state or not state.startswith("awaiting_"):
            return None

        reply = self._process_fsm_input(chat_id, state, ctx or {}, text.strip())
        try:
            from newsbrief.bot import fsm as _fsm
            _fsm.clear_user_state(str(chat_id), self.storage)
        except Exception:
            pass
        return reply

    def _process_fsm_input(self, chat_id: str, state: str, ctx: dict, text: str) -> str:
        """Apply the text value based on the current state."""
        base = state.split(":", 1)[0]
        if base == "awaiting_schedule_input":
            if not _valid_hhmm(text):
                return "❌ Формат HH:MM. Попробуй ещё раз."
            if self.config:
                self.config.schedule.send_at = text
                try:
                    self.config.save()
                except Exception:
                    pass
            return f"✅ Время доставки: <b>{text}</b>"
        if base == "awaiting_llm_key":
            preset = ctx.get("preset") or (state.split(":", 1)[1] if ":" in state else "")
            if self.config:
                self.config.llm.api_key = text
                if preset:
                    self.config.llm.preset = preset
                try:
                    self.config.save()
                except Exception:
                    pass
            return f"✅ API key сохранён для <b>{preset or 'LLM'}</b>."
        if base == "awaiting_profile_text":
            if self.config:
                self.config.user.profile = text
                try:
                    self.config.save()
                except Exception:
                    pass
            return "✅ Профиль обновлён."
        if base == "awaiting_interests_text":
            topic_id = ctx.get("topic_id") or (state.split(":", 1)[1] if ":" in state else "")
            if self.config and topic_id:
                for t in self.config.topics:
                    if t.id == topic_id:
                        t.interests_boost = [x.strip() for x in text.split(",") if x.strip()]
                        break
                try:
                    self.config.save()
                except Exception:
                    pass
            return "✅ Интересы обновлены."
        if base == "awaiting_rss_url":
            topic_id = ctx.get("topic_id", "")
            if self.config and topic_id:
                for t in self.config.topics:
                    if t.id == topic_id:
                        srcs = t.sources if isinstance(t.sources, dict) else {}
                        rss_list = list(srcs.get("rss") or [])
                        rss_list.append(text)
                        srcs["rss"] = rss_list
                        t.sources = srcs
                        break
                try:
                    self.config.save()
                except Exception:
                    pass
            return "✅ Источник добавлен."
        if base == "awaiting_items_limit":
            try:
                n = max(1, min(20, int(text)))
            except Exception:
                return "❌ Введи число от 1 до 20."
            topic_id = ctx.get("topic_id", "")
            if self.config and topic_id:
                for t in self.config.topics:
                    if t.id == topic_id:
                        t.items_per_digest = n
                        break
                try:
                    self.config.save()
                except Exception:
                    pass
            return f"✅ Лимит: <b>{n}</b>."
        if base == "awaiting_topic_name":
            name = text.strip()
            if not name:
                return "❌ Пустое название."
            tid = name.lower().replace(" ", "_")[:32]
            if self.config:
                from newsbrief.config import TopicConfig
                self.config.topics.append(TopicConfig(id=tid, name=name))
                try:
                    self.config.save()
                except Exception:
                    pass
            return f"✅ Тема <b>{name}</b> добавлена."
        return "(неизвестное состояние ввода)"

    def handle_schedule(self, chat_id: str, args: str = "") -> str:
        """Set delivery time. Usage: /schedule 09:30"""
        if not args:
            current = self.config.schedule.send_at if self.config else "09:00"
            return (
                f"⏰ Текущее время: <b>{current}</b>\n"
                f"Использование: <code>/schedule 09:30</code>"
            )
        new_time = args.strip()
        if not _valid_hhmm(new_time):
            return "❌ Неверный формат. Пример: <code>/schedule 09:30</code>"

        if self.on_schedule:
            try:
                self.on_schedule(new_time)
            except Exception as e:
                return f"❌ Ошибка: {e}"
        elif self.config:
            self.config.schedule.send_at = new_time
            try:
                self.config.save()
            except Exception as e:
                logger.warning("[bot] config save failed: %s", e)

        return f"✅ Время доставки обновлено: <b>{new_time}</b>"

    # --- dispatch ------------------------------------------------------

    def dispatch(self, text: str, chat_id: str) -> Optional[str]:
        if not text or not text.startswith("/"):
            return None
        parts = text.strip().split(maxsplit=1)
        cmd = parts[0].split("@")[0].lower()  # strip @botname
        args = parts[1] if len(parts) > 1 else ""

        handlers = {
            "/start":    lambda: self.handle_start(chat_id),
            "/digest":   lambda: self.handle_digest(chat_id),
            "/stats":    lambda: self.handle_stats(chat_id),
            "/pause":    lambda: self.handle_pause(chat_id),
            "/resume":   lambda: self.handle_resume(chat_id),
            "/menu":     lambda: self.handle_menu(chat_id),
            "/schedule": lambda: self.handle_schedule(chat_id, args),
        }
        handler = handlers.get(cmd)
        if not handler:
            return None
        return handler()

    # --- polling loop --------------------------------------------------

    def poll_once(self, client: httpx.Client) -> int:
        """Poll once via getUpdates. Returns number of updates processed."""
        url = f"{TELEGRAM_API_BASE}/bot{self.channel.bot_token}/getUpdates"
        params = {
            "timeout": POLL_TIMEOUT_SEC,
            "offset":  self._last_update_id + 1 if self._last_update_id else None,
        }
        params = {k: v for k, v in params.items() if v is not None}
        try:
            resp = client.get(url, params=params, timeout=POLL_TIMEOUT_SEC + 5)
            resp.raise_for_status()
            updates = resp.json().get("result", [])
        except Exception as e:
            logger.warning("[bot] getUpdates failed: %s", e)
            return 0

        for upd in updates:
            self._last_update_id = max(self._last_update_id, upd.get("update_id", 0))
            msg = upd.get("message") or upd.get("edited_message")
            if not msg:
                continue
            chat_id = str(msg.get("chat", {}).get("id", ""))
            text    = msg.get("text", "")
            # Non-command text: first check FSM awaiting-input states
            if text and not text.startswith("/"):
                fsm_reply = self.handle_text_input(chat_id, text)
                if fsm_reply is not None:
                    self.channel.send([fsm_reply], meta={"chat_id": chat_id})
                    continue
            reply = self.dispatch(text, chat_id)
            if reply:
                self.channel.send([reply], meta={"chat_id": chat_id})
        return len(updates)

    def run_polling(self) -> None:
        """Blocking polling loop."""
        if not self.channel.bot_token:
            logger.warning("[bot] no token — polling disabled")
            return
        self._running = True
        logger.info("[bot] starting long-polling loop")
        with httpx.Client() as client:
            while self._running:
                try:
                    self.poll_once(client)
                except KeyboardInterrupt:
                    break
                except Exception as e:
                    logger.error("[bot] poll error: %s", e)
                    time.sleep(5)
        logger.info("[bot] polling stopped")

    def stop(self) -> None:
        self._running = False


def _valid_hhmm(s: str) -> bool:
    try:
        hh, mm = s.split(":")
        h, m = int(hh), int(mm)
        return 0 <= h <= 23 and 0 <= m <= 59
    except (ValueError, AttributeError):
        return False
