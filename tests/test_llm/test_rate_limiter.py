"""Tests for TokenBucket and retry-delay helper."""
from __future__ import annotations

import time

from newsbrief.llm.rate_limiter import (
    MAX_RETRIES,
    RETRY_DELAYS,
    TokenBucket,
    compute_retry_delay,
)


def test_bucket_allows_initial_burst_up_to_capacity():
    b = TokenBucket(rpm=60)
    # Bucket starts full; 3 sequential acquires must succeed immediately.
    t0 = time.monotonic()
    for _ in range(3):
        assert b.acquire(max_wait=1.0) is True
    assert time.monotonic() - t0 < 0.2  # effectively instant


def test_bucket_blocks_when_empty_then_refills():
    b = TokenBucket(rpm=600)  # 10 req/sec → refill in ~100ms per token
    # Drain.
    for _ in range(5):
        assert b.acquire(max_wait=0.5) is True
    # Force empty by draining capacity exactly.
    # Capacity == rpm == 600; we've only used 5 → still plenty. Use smaller bucket.
    b2 = TokenBucket(rpm=60)  # 1 req/sec
    for _ in range(60):
        assert b2.acquire(max_wait=0.0) is True
    t0 = time.monotonic()
    # Next one must wait ~1s (but we only allow 3s max).
    assert b2.acquire(max_wait=3.0) is True
    elapsed = time.monotonic() - t0
    assert 0.5 < elapsed < 2.5


def test_bucket_respects_max_wait_timeout():
    b = TokenBucket(rpm=1)  # 1 req/min
    assert b.acquire(max_wait=0.0) is True  # consume initial
    # Second acquire would need ~60s; we cap wait at 0.1s.
    t0 = time.monotonic()
    ok = b.acquire(max_wait=0.1)
    elapsed = time.monotonic() - t0
    assert ok is False
    assert elapsed < 0.5


def test_bucket_snapshot_fields():
    b = TokenBucket(rpm=30, tpm=1000, rpd=500)
    snap = b.snapshot()
    assert snap["rpm"] == 30
    assert snap["tpm"] == 1000
    assert snap["rpd"] == 500
    assert snap["req_available"] <= 30
    assert snap["day_used"] == 0


def test_compute_retry_delay_sequence():
    assert compute_retry_delay(1) == RETRY_DELAYS[0]
    assert compute_retry_delay(2) == RETRY_DELAYS[1]
    assert compute_retry_delay(3) == RETRY_DELAYS[2]
    assert compute_retry_delay(4) == RETRY_DELAYS[3]
    # Beyond max: saturates.
    assert compute_retry_delay(10) == RETRY_DELAYS[-1]


def test_compute_retry_delay_respects_retry_after():
    assert compute_retry_delay(2, retry_after=7.5) == 7.5
    assert compute_retry_delay(1, retry_after=0) == 0.0


def test_max_retries_is_four():
    assert MAX_RETRIES == 4
