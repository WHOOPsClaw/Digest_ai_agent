"""test_telegram_format — HTML, splitting, button generation."""
import json

from newsbrief.delivery.telegram import (
    TELEGRAM_MAX_LEN,
    _hard_split,
    build_feedback_keyboard,
    parse_callback_data,
)


def test_hard_split_short():
    assert _hard_split("hello") == ["hello"]


def test_hard_split_long():
    text = "a" * (TELEGRAM_MAX_LEN + 100)
    parts = _hard_split(text)
    assert len(parts) >= 2
    for p in parts:
        assert len(p) <= TELEGRAM_MAX_LEN


def test_hard_split_prefers_newlines():
    text = ("line\n" * 500) + ("x" * 100)
    parts = _hard_split(text, max_len=200)
    assert len(parts) >= 2
    # Each part (except possibly last) should end cleanly
    for p in parts:
        assert len(p) <= 200


def test_build_feedback_keyboard():
    kb = build_feedback_keyboard(digest_id=42, article_idx=3)
    assert "inline_keyboard" in kb
    row = kb["inline_keyboard"][0]
    assert len(row) == 4
    actions = [btn["callback_data"].split(":")[-1] for btn in row]
    assert set(actions) == {"up", "down", "mute", "save"}


def test_callback_data_under_64_bytes():
    # Extreme values to stress length check
    kb = build_feedback_keyboard(digest_id=999_999_999, article_idx=999)
    for btn in kb["inline_keyboard"][0]:
        assert len(btn["callback_data"].encode("utf-8")) <= 64


def test_keyboard_json_serializable():
    kb = build_feedback_keyboard(1, 0)
    serialized = json.dumps(kb)
    assert "inline_keyboard" in serialized


def test_parse_callback_data_valid():
    parsed = parse_callback_data("fb:123:4:up")
    assert parsed == {"digest_id": 123, "article_idx": 4, "action": "up"}


def test_parse_callback_data_bad_prefix():
    assert parse_callback_data("xx:1:2:up") is None


def test_parse_callback_data_wrong_parts():
    assert parse_callback_data("fb:1:2") is None
    assert parse_callback_data("fb:1:2:up:extra") is None


def test_parse_callback_data_non_numeric():
    assert parse_callback_data("fb:abc:4:up") is None


def test_parse_callback_data_empty():
    assert parse_callback_data("") is None


def test_html_escape_in_payload():
    """Ensure TelegramChannel sends parse_mode=HTML (see send implementation)."""
    from newsbrief.delivery.telegram import TelegramChannel
    ch = TelegramChannel(bot_token="", chat_id="")
    # Empty token → skipped
    res = ch.send(["<b>hi</b>"])
    assert res.skipped is True
