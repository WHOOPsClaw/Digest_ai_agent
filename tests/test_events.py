"""Tests for digest/events.py — grouping, timezone handling."""
import pytest
import sys
import os
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from newsbrief.processing.events import _time_close, _ensure_utc


class TestEnsureUtc:
    def test_none_returns_none(self):
        assert _ensure_utc(None) is None

    def test_naive_gets_utc(self):
        dt = datetime(2026, 4, 15, 10, 0, 0)
        result = _ensure_utc(dt)
        assert result.tzinfo == timezone.utc
        assert result.hour == 10

    def test_aware_utc_unchanged(self):
        dt = datetime(2026, 4, 15, 10, 0, 0, tzinfo=timezone.utc)
        result = _ensure_utc(dt)
        assert result == dt

    def test_aware_non_utc_converted(self):
        tz_moscow = timezone(timedelta(hours=3))
        dt = datetime(2026, 4, 15, 13, 0, 0, tzinfo=tz_moscow)  # 13:00 MSK = 10:00 UTC
        result = _ensure_utc(dt)
        assert result.tzinfo == timezone.utc
        assert result.hour == 10


class TestTimeClose:
    def test_both_none(self):
        assert _time_close(None, None) is True

    def test_one_none(self):
        dt = datetime(2026, 4, 15, 10, 0, 0, tzinfo=timezone.utc)
        assert _time_close(dt, None) is True
        assert _time_close(None, dt) is True

    def test_same_time(self):
        dt = datetime(2026, 4, 15, 10, 0, 0, tzinfo=timezone.utc)
        assert _time_close(dt, dt) is True

    def test_within_window(self):
        dt1 = datetime(2026, 4, 15, 10, 0, 0, tzinfo=timezone.utc)
        dt2 = datetime(2026, 4, 15, 20, 0, 0, tzinfo=timezone.utc)  # 10h apart
        assert _time_close(dt1, dt2) is True  # default MAX_TIME_DELTA_H is 24

    def test_outside_window(self):
        dt1 = datetime(2026, 4, 15, 10, 0, 0, tzinfo=timezone.utc)
        dt2 = datetime(2026, 4, 17, 10, 0, 0, tzinfo=timezone.utc)  # 48h apart
        assert _time_close(dt1, dt2) is False

    def test_mixed_naive_aware_no_crash(self):
        """This was a latent bug — naive vs aware comparison."""
        naive = datetime(2026, 4, 15, 10, 0, 0)
        aware = datetime(2026, 4, 15, 10, 0, 0, tzinfo=timezone.utc)
        # Should NOT raise TypeError
        result = _time_close(naive, aware)
        assert isinstance(result, bool)

    def test_mixed_timezones_no_crash(self):
        tz_moscow = timezone(timedelta(hours=3))
        utc_dt = datetime(2026, 4, 15, 10, 0, 0, tzinfo=timezone.utc)
        msk_dt = datetime(2026, 4, 15, 13, 0, 0, tzinfo=tz_moscow)
        # Same moment in time — should be close
        assert _time_close(utc_dt, msk_dt) is True
