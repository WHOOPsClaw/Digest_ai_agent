"""delivery/base.py — base abstractions for delivery channels."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DeliveryResult:
    ok:          bool
    sent_parts:  int  = 0
    total_parts: int  = 0
    errors:      list = field(default_factory=list)
    skipped:     bool = False
    skip_reason: str  = ""
    message_ids: list = field(default_factory=list)


class DeliveryChannel(ABC):
    """Abstract base for any delivery channel (telegram, email, etc.)."""

    channel_id: str = "base"

    @abstractmethod
    def send(self, parts: list[str], meta: Optional[dict] = None) -> DeliveryResult:
        """Send pre-split message parts. meta may carry digest_id, chat_id, etc."""
        ...

    def test(self) -> dict:
        """Send a test message. Returns {'ok': bool, 'error'?: str}."""
        try:
            result = self.send(["<b>newsbrief</b> test message"], meta={"test": True})
            if result.ok or result.skipped:
                return {"ok": True, "skipped": result.skipped, "reason": result.skip_reason}
            return {"ok": False, "error": "; ".join(result.errors) or "unknown"}
        except Exception as e:
            return {"ok": False, "error": str(e)}
