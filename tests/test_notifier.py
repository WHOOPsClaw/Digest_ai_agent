"""Tests for digest/notifier.py — structure and config tests (no real Telegram calls)."""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from newsbrief.delivery._legacy_telegram import send_digest_to_user, NotifyResult


class TestSendDigestToUser:
    def test_empty_parts_returns_skipped(self):
        result = send_digest_to_user("12345", [])
        assert result.skipped is True
        assert result.success is False

    def test_no_token_returns_skipped(self, monkeypatch):
        monkeypatch.setattr("newsbrief.delivery._legacy_telegram.TELEGRAM_TOKEN", "")
        result = send_digest_to_user("12345", ["Hello"])
        assert result.skipped is True

    def test_empty_chat_id_returns_skipped(self):
        result = send_digest_to_user("", ["Hello"])
        assert result.skipped is True


class TestNotifyResult:
    def test_dataclass_fields(self):
        r = NotifyResult(success=True, total_parts=5, sent_parts=3, failed_parts=2)
        assert r.success is True
        assert r.total_parts == 5
        assert r.sent_parts == 3
        assert r.failed_parts == 2
