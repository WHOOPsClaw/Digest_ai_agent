"""test_scheduler — build-time math and adaptive buffer."""
from newsbrief.core.scheduler import (
    BUFFER_DEFAULTS,
    calculate_build_time,
    calculate_buffer_minutes,
    update_buffer_from_history,
)


class _FakeStorage:
    """Simulated storage returning fixed pipeline_runs rows."""
    def __init__(self, durations_sec):
        self.durations = durations_sec

    def fetchall(self, sql, params=()):
        return [{"duration_sec": d} for d in self.durations]


def test_build_time_default_groq():
    # groq buffer = 15 min; 09:00 - 15 = 08:45
    assert calculate_build_time("09:00", "groq") == "08:45"


def test_build_time_default_deepseek():
    # deepseek = 40 min; 09:00 - 40 = 08:20
    assert calculate_build_time("09:00", "deepseek") == "08:20"


def test_build_time_unknown_preset_falls_back():
    # default = 30 min
    assert calculate_build_time("10:00", "unknown-provider") == "09:30"


def test_build_time_override_buffer():
    assert calculate_build_time("09:00", "groq", override_buffer=10) == "08:50"


def test_build_time_wraps_past_midnight():
    # 00:05 - 30 = 23:35
    assert calculate_build_time("00:05", "openai") == "23:35"


def test_buffer_defaults_registered():
    for p in ["groq", "cerebras", "gemini", "mistral", "openai",
              "anthropic", "openrouter", "deepseek"]:
        assert p in BUFFER_DEFAULTS


def test_rolling_avg_used_when_enough_samples():
    # 7 runs of 600 sec (10 min) → avg 10 min × 1.3 = 13 min
    storage = _FakeStorage([600.0] * 7)
    buf = calculate_buffer_minutes("groq", storage=storage)
    assert buf == 13


def test_rolling_avg_ignored_when_too_few():
    storage = _FakeStorage([600.0] * 3)  # <7 samples
    buf = calculate_buffer_minutes("groq", storage=storage)
    assert buf == BUFFER_DEFAULTS["groq"]  # = 15


def test_rolling_avg_respects_override():
    storage = _FakeStorage([6000.0] * 10)  # huge durations
    buf = calculate_buffer_minutes("groq", override_buffer=20, storage=storage)
    assert buf == 20  # override wins


def test_buffer_clamped():
    # Extreme rolling avg → clamped to <=120
    storage = _FakeStorage([100_000.0] * 7)
    buf = calculate_buffer_minutes("groq", storage=storage)
    assert buf == 120


def test_update_buffer_from_history_detects_big_change(caplog):
    storage = _FakeStorage([900.0] * 7)  # avg 15 min × 1.3 ≈ 20
    new = update_buffer_from_history(storage, current_buffer=5)
    assert new > 5  # changed
