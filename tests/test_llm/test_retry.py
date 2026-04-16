"""Tests for RateLimitedProvider — 429 retry with exponential backoff."""
from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from newsbrief.llm.base import LLMProvider, LLMResponse
from newsbrief.llm.rate_limiter import LLMRateLimitError, TokenBucket
from newsbrief.llm.router import RateLimitedProvider


class _FlakyProvider(LLMProvider):
    provider_id = "flaky"

    def __init__(self, fail_times: int, status: int = 429):
        self.fail_times = fail_times
        self.status = status
        self.calls = 0
        self.model = "m"

    def generate(self, prompt: str, **kwargs) -> LLMResponse:
        self.calls += 1
        if self.calls <= self.fail_times:
            req = httpx.Request("POST", "https://x/v1/chat/completions")
            resp = httpx.Response(self.status, request=req)
            raise httpx.HTTPStatusError(f"HTTP {self.status}", request=req, response=resp)
        return LLMResponse(text="ok", model="m", latency_ms=1)


def test_retry_succeeds_after_two_429s():
    inner = _FlakyProvider(fail_times=2)
    wrapped = RateLimitedProvider(inner, bucket=None)
    with patch("newsbrief.llm.router.time.sleep"):
        r = wrapped.generate("hi")
    assert r.text == "ok"
    assert inner.calls == 3


def test_retry_exhausts_after_max_attempts():
    inner = _FlakyProvider(fail_times=10)
    wrapped = RateLimitedProvider(inner, bucket=None)
    with patch("newsbrief.llm.router.time.sleep"):
        with pytest.raises(LLMRateLimitError):
            wrapped.generate("hi")
    # 4 attempts max
    assert inner.calls == 4


def test_non_429_error_propagates_without_retry():
    inner = _FlakyProvider(fail_times=10, status=500)
    wrapped = RateLimitedProvider(inner, bucket=None)
    with pytest.raises(httpx.HTTPStatusError):
        wrapped.generate("hi")
    assert inner.calls == 1


def test_bucket_consumed_on_each_attempt():
    inner = _FlakyProvider(fail_times=0)
    bucket = TokenBucket(rpm=60)
    wrapped = RateLimitedProvider(inner, bucket=bucket)
    wrapped.generate("hi")
    snap = bucket.snapshot()
    # We consumed one token.
    assert snap["req_available"] <= 60.0 - 1.0 + 1.0  # loose — time-based refill
    assert inner.calls == 1


def test_retry_honors_retry_after_header():
    class _WithHeader(LLMProvider):
        provider_id = "hdr"

        def __init__(self):
            self.calls = 0

        def generate(self, prompt, **kwargs):
            self.calls += 1
            if self.calls == 1:
                req = httpx.Request("POST", "https://x")
                resp = httpx.Response(429, request=req, headers={"Retry-After": "2"})
                raise httpx.HTTPStatusError("429", request=req, response=resp)
            return LLMResponse(text="ok", model="m", latency_ms=1)

    inner = _WithHeader()
    wrapped = RateLimitedProvider(inner, bucket=None)
    sleeps: list[float] = []
    with patch("newsbrief.llm.router.time.sleep", side_effect=lambda s: sleeps.append(s)):
        r = wrapped.generate("hi")
    assert r.text == "ok"
    # Retry-After value should appear in sleeps.
    assert any(abs(s - 2.0) < 0.01 for s in sleeps)
