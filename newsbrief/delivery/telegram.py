"""delivery/telegram.py — Telegram delivery channel.

HTML parse_mode, auto-split at 4096 chars, inline feedback buttons on cards,
retry once on 5xx, load token from config.
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import List, Optional

import httpx

from newsbrief.delivery.base import DeliveryChannel, DeliveryResult

logger = logging.getLogger("newsbrief")

TELEGRAM_API_BASE  = os.getenv("TELEGRAM_API_BASE", "https://api.telegram.org")
TELEGRAM_TIMEOUT   = float(os.getenv("TELEGRAM_TIMEOUT", "15"))
TELEGRAM_SEND_DELAY = float(os.getenv("TELEGRAM_SEND_DELAY", "1.0"))
TELEGRAM_MAX_LEN   = 4096  # hard Telegram limit
RETRY_DELAY_SEC    = 2.0


# ---------------------------------------------------------------------------
# Hard split (safety net — composer already splits but enforce 4096)
# ---------------------------------------------------------------------------

def _hard_split(text: str, max_len: int = TELEGRAM_MAX_LEN) -> List[str]:
    """Split `text` so each chunk ≤ max_len, preferring newline boundaries."""
    if len(text) <= max_len:
        return [text]
    parts: List[str] = []
    remaining = text
    while len(remaining) > max_len:
        chunk = remaining[:max_len]
        pos   = chunk.rfind("\n\n")
        if pos < max_len // 4:
            pos = chunk.rfind("\n")
        if pos <= 0:
            pos = max_len
        parts.append(remaining[:pos].rstrip())
        remaining = remaining[pos:].lstrip()
    if remaining:
        parts.append(remaining)
    return parts


# ---------------------------------------------------------------------------
# Inline keyboard for feedback buttons
# ---------------------------------------------------------------------------

def build_feedback_keyboard(digest_id: int, article_idx: int) -> dict:
    """Build inline keyboard for one card.

    callback_data format: "fb:{digest_id}:{article_idx}:{action}"
    Must stay < 64 bytes.
    """
    row = [
        {"text": "👍", "callback_data": f"fb:{digest_id}:{article_idx}:up"},
        {"text": "👎", "callback_data": f"fb:{digest_id}:{article_idx}:down"},
        {"text": "🔕", "callback_data": f"fb:{digest_id}:{article_idx}:mute"},
        {"text": "📌", "callback_data": f"fb:{digest_id}:{article_idx}:save"},
    ]
    # Sanity: each callback_data must be ≤ 64 bytes
    for btn in row:
        assert len(btn["callback_data"].encode("utf-8")) <= 64, "callback_data too long"
    return {"inline_keyboard": [row]}


def build_inline_keyboard(rows: list) -> dict:
    """Convert [[{text, callback_data}, ...], ...] → Telegram inline_keyboard dict.

    Accepts rows already in Telegram-compatible shape; if given a flat list of
    buttons, wraps it in one row. Buttons missing ``callback_data`` pass-through
    (supports ``url`` buttons).
    """
    if not rows:
        return {"inline_keyboard": []}
    # Flat list of button dicts → one row
    if isinstance(rows[0], dict):
        rows = [rows]  # type: ignore[list-item]
    clean: list = []
    for row in rows:
        clean_row = []
        for btn in row:
            if not isinstance(btn, dict):
                continue
            out = {"text": str(btn.get("text", "?"))}
            if "callback_data" in btn:
                cd = str(btn["callback_data"])
                # enforce 64-byte limit
                if len(cd.encode("utf-8")) <= 64:
                    out["callback_data"] = cd
                else:
                    out["callback_data"] = cd.encode("utf-8")[:64].decode("utf-8", "ignore")
            if "url" in btn:
                out["url"] = str(btn["url"])
            clean_row.append(out)
        if clean_row:
            clean.append(clean_row)
    return {"inline_keyboard": clean}


def parse_callback_data(data: str) -> Optional[dict]:
    """Parse "fb:{digest_id}:{article_idx}:{action}" → dict or None."""
    try:
        parts = data.split(":")
        if len(parts) != 4 or parts[0] != "fb":
            return None
        return {
            "digest_id":   int(parts[1]),
            "article_idx": int(parts[2]),
            "action":      parts[3],
        }
    except (ValueError, IndexError):
        return None


# ---------------------------------------------------------------------------
# Low-level send helpers
# ---------------------------------------------------------------------------

def _post_with_retry(
    client: httpx.Client,
    url: str,
    payload: dict,
    files: Optional[dict] = None,
) -> httpx.Response:
    """POST with one retry on 5xx / network error. Raises on final failure."""
    attempt = 0
    last_exc: Optional[Exception] = None
    while attempt < 2:
        attempt += 1
        try:
            if files:
                resp = client.post(url, data=payload, files=files, timeout=TELEGRAM_TIMEOUT)
            else:
                resp = client.post(url, json=payload, timeout=TELEGRAM_TIMEOUT)
            if resp.status_code >= 500:
                last_exc = httpx.HTTPStatusError(
                    f"HTTP {resp.status_code}", request=resp.request, response=resp
                )
                if attempt < 2:
                    time.sleep(RETRY_DELAY_SEC)
                    continue
                resp.raise_for_status()
            resp.raise_for_status()
            return resp
        except httpx.RequestError as e:
            last_exc = e
            if attempt < 2:
                time.sleep(RETRY_DELAY_SEC)
                continue
            raise
    # Unreachable, but satisfy type-checkers
    raise last_exc  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Channel
# ---------------------------------------------------------------------------

class TelegramChannel(DeliveryChannel):
    channel_id = "telegram"

    def __init__(self, bot_token: str = "", chat_id: str = "", feedback_buttons: bool = False):
        self.bot_token = bot_token or os.getenv("TELEGRAM_TOKEN", "")
        self.chat_id   = str(chat_id or os.getenv("TELEGRAM_CHAT_ID", ""))
        self.feedback_buttons = bool(feedback_buttons)

    @classmethod
    def from_config(cls, config) -> "TelegramChannel":
        tg = config.delivery.telegram
        fb = bool(getattr(getattr(config, "format", None), "feedback_buttons", False))
        return cls(bot_token=tg.bot_token, chat_id=tg.chat_id, feedback_buttons=fb)

    # --- main send -----------------------------------------------------

    def send(self, parts: List[str], meta: Optional[dict] = None) -> DeliveryResult:
        meta = meta or {}
        chat_id = str(meta.get("chat_id") or self.chat_id)

        if not self.bot_token:
            return DeliveryResult(
                ok=False, total_parts=len(parts), skipped=True,
                skip_reason="TELEGRAM_TOKEN not set",
            )
        if not chat_id:
            return DeliveryResult(
                ok=False, total_parts=len(parts), skipped=True,
                skip_reason="chat_id is empty",
            )
        if not parts:
            return DeliveryResult(ok=True, total_parts=0, sent_parts=0)

        # Safety: enforce 4096-char limit by hard-splitting oversized input
        safe_parts: List[str] = []
        for p in parts:
            safe_parts.extend(_hard_split(p))

        url = f"{TELEGRAM_API_BASE}/bot{self.bot_token}/sendMessage"
        msg_ids: List[int] = []
        errors:  List[str] = []

        with httpx.Client() as client:
            for i, part in enumerate(safe_parts):
                if i > 0:
                    time.sleep(TELEGRAM_SEND_DELAY)
                payload = {
                    "chat_id":                  chat_id,
                    "text":                     part,
                    "parse_mode":               "HTML",
                    "disable_web_page_preview": True,
                }
                try:
                    resp = _post_with_retry(client, url, payload)
                    msg_ids.append(resp.json()["result"]["message_id"])
                except httpx.HTTPStatusError as e:
                    errors.append(f"part {i+1}: HTTP {e.response.status_code} — {e.response.text[:120]}")
                    logger.error("[telegram] %s", errors[-1])
                except httpx.RequestError as e:
                    errors.append(f"part {i+1}: network error — {e}")
                    logger.error("[telegram] %s", errors[-1])

        ok = len(errors) == 0 and len(msg_ids) == len(safe_parts)
        return DeliveryResult(
            ok=ok,
            sent_parts=len(msg_ids),
            total_parts=len(safe_parts),
            errors=errors,
            message_ids=msg_ids,
        )

    # --- digest with feedback buttons ----------------------------------

    def send_digest(
        self,
        parts: List[str],
        digest_id: int,
        chat_id: Optional[str] = None,
    ) -> DeliveryResult:
        """Send digest parts; attach feedback keyboard to each 'card' part.

        Heuristic: the first part (header/headlines section) gets no buttons.
        Each subsequent part is treated as a card group and gets buttons for
        index = part_index (the whole section level).
        """
        target_chat = str(chat_id or self.chat_id)
        if not self.bot_token:
            return DeliveryResult(ok=False, total_parts=len(parts), skipped=True,
                                  skip_reason="TELEGRAM_TOKEN not set")
        if not target_chat:
            return DeliveryResult(ok=False, total_parts=len(parts), skipped=True,
                                  skip_reason="chat_id is empty")
        if not parts:
            return DeliveryResult(ok=True, total_parts=0, sent_parts=0)

        safe_parts: List[str] = []
        for p in parts:
            safe_parts.extend(_hard_split(p))

        url = f"{TELEGRAM_API_BASE}/bot{self.bot_token}/sendMessage"
        msg_ids: List[int] = []
        errors:  List[str] = []

        with httpx.Client() as client:
            for i, part in enumerate(safe_parts):
                if i > 0:
                    time.sleep(TELEGRAM_SEND_DELAY)
                payload = {
                    "chat_id":                  target_chat,
                    "text":                     part,
                    "parse_mode":               "HTML",
                    "disable_web_page_preview": True,
                }
                # First part (header/headlines) has no feedback buttons.
                # Skip entirely when feedback_buttons is disabled (default).
                if i > 0 and self.feedback_buttons:
                    kb = build_feedback_keyboard(digest_id, i)
                    payload["reply_markup"] = json.dumps(kb)
                try:
                    resp = _post_with_retry(client, url, payload)
                    msg_ids.append(resp.json()["result"]["message_id"])
                except httpx.HTTPStatusError as e:
                    errors.append(f"part {i+1}: HTTP {e.response.status_code} — {e.response.text[:120]}")
                    logger.error("[telegram] %s", errors[-1])
                except httpx.RequestError as e:
                    errors.append(f"part {i+1}: network error — {e}")
                    logger.error("[telegram] %s", errors[-1])

        ok = len(errors) == 0 and len(msg_ids) == len(safe_parts)
        return DeliveryResult(
            ok=ok,
            sent_parts=len(msg_ids),
            total_parts=len(safe_parts),
            errors=errors,
            message_ids=msg_ids,
        )

    # --- photo ---------------------------------------------------------

    def send_photo(
        self,
        png_bytes: bytes,
        caption: str = "",
        chat_id: Optional[str] = None,
    ) -> DeliveryResult:
        target_chat = str(chat_id or self.chat_id)
        if not self.bot_token or not target_chat:
            return DeliveryResult(
                ok=False, total_parts=1, skipped=True,
                skip_reason="token or chat_id missing",
            )

        url = f"{TELEGRAM_API_BASE}/bot{self.bot_token}/sendPhoto"
        data = {
            "chat_id":    target_chat,
            "caption":    caption[:1024],
            "parse_mode": "HTML",
        }
        files = {"photo": ("chart.png", png_bytes, "image/png")}

        with httpx.Client() as client:
            try:
                resp = _post_with_retry(client, url, data, files=files)
                return DeliveryResult(
                    ok=True, sent_parts=1, total_parts=1,
                    message_ids=[resp.json()["result"]["message_id"]],
                )
            except httpx.HTTPStatusError as e:
                err = f"HTTP {e.response.status_code} — {e.response.text[:120]}"
                logger.error("[telegram] send_photo: %s", err)
                return DeliveryResult(ok=False, total_parts=1, errors=[err])
            except httpx.RequestError as e:
                err = f"network error — {e}"
                logger.error("[telegram] send_photo: %s", err)
                return DeliveryResult(ok=False, total_parts=1, errors=[err])

    # --- inline keyboard helpers (settings UI) -------------------------

    def send_with_keyboard(
        self,
        chat_id: str,
        text: str,
        keyboard: list,
        parse_mode: str = "HTML",
    ) -> int:
        """Send a new message with an inline keyboard. Returns message_id (0 on failure)."""
        if not self.bot_token or not chat_id:
            return 0
        url = f"{TELEGRAM_API_BASE}/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": str(chat_id),
            "text": text[:TELEGRAM_MAX_LEN],
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
            "reply_markup": json.dumps(build_inline_keyboard(keyboard)),
        }
        try:
            with httpx.Client() as client:
                resp = _post_with_retry(client, url, payload)
                return int(resp.json()["result"]["message_id"])
        except Exception as e:
            logger.warning("[telegram] send_with_keyboard failed: %s", e)
            return 0

    def edit_message_text(
        self,
        chat_id: str,
        message_id: int,
        text: str,
        keyboard: Optional[list] = None,
        parse_mode: str = "HTML",
    ) -> bool:
        """Call editMessageText. Returns True on success."""
        if not self.bot_token or not chat_id:
            return False
        url = f"{TELEGRAM_API_BASE}/bot{self.bot_token}/editMessageText"
        payload = {
            "chat_id": str(chat_id),
            "message_id": int(message_id),
            "text": text[:TELEGRAM_MAX_LEN],
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }
        if keyboard is not None:
            payload["reply_markup"] = json.dumps(build_inline_keyboard(keyboard))
        try:
            with httpx.Client() as client:
                resp = client.post(url, json=payload, timeout=TELEGRAM_TIMEOUT)
                resp.raise_for_status()
                return True
        except Exception as e:
            logger.warning("[telegram] edit_message_text failed: %s", e)
            return False

    # --- callback ack --------------------------------------------------

    def answer_callback_query(self, callback_query_id: str, text: str = "") -> bool:
        if not self.bot_token:
            return False
        url = f"{TELEGRAM_API_BASE}/bot{self.bot_token}/answerCallbackQuery"
        payload = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text[:200]
        try:
            with httpx.Client() as client:
                resp = client.post(url, json=payload, timeout=TELEGRAM_TIMEOUT)
                resp.raise_for_status()
                return True
        except Exception as e:
            logger.warning("[telegram] answerCallbackQuery failed: %s", e)
            return False
