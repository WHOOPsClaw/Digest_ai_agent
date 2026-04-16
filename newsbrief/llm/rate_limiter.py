"""llm/rate_limiter.py — token-bucket rate limiter for LLM providers.

Used to throttle calls to free-tier APIs (Groq 30 RPM, Gemini 15 RPM, ...).
Each provider gets its own TokenBucket instance; acquire() blocks until a
request slot is available, up to `max_wait` seconds.

Also provides LLMRateLimitError for callers that need to surface 429s.
"""
from __future__ import annotations

import threading
import time
from typing import Optional


class LLMRateLimitError(RuntimeError):
    """Raised after all retries fail with 429 / rate-limit exhaustion."""


class TokenBucket:
    """Simple thread-safe token bucket.

    Refills `rpm` tokens per 60 seconds (linearly). Optional `tpm` tracks
    tokens-per-minute for models that meter by prompt size; when set,
    acquire(tokens=N) also consumes N from the tpm budget.

    Not distributed — per-process only. Good enough for a single pipeline run.
    """

    def __init__(self, rpm: int, tpm: Optional[int] = None, rpd: Optional[int] = None) -> None:
        self.rpm = max(1, int(rpm))
        self.tpm = int(tpm) if tpm else None
        self.rpd = int(rpd) if rpd else None

        self._capacity_req = float(self.rpm)
        self._tokens_req = float(self.rpm)
        self._rate_req = float(self.rpm) / 60.0  # per second

        self._capacity_tok = float(self.tpm) if self.tpm else 0.0
        self._tokens_tok = float(self.tpm) if self.tpm else 0.0
        self._rate_tok = (float(self.tpm) / 60.0) if self.tpm else 0.0

        self._last_refill = time.monotonic()
        self._day_start = time.monotonic()
        self._day_used = 0

        self._lock = threading.Lock()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        if elapsed <= 0:
            return
        self._tokens_req = min(self._capacity_req, self._tokens_req + elapsed * self._rate_req)
        if self.tpm:
            self._tokens_tok = min(self._capacity_tok, self._tokens_tok + elapsed * self._rate_tok)
        self._last_refill = now

        # Daily counter reset (24h rolling window — approximated).
        if self.rpd and (now - self._day_start) >= 86400:
            self._day_start = now
            self._day_used = 0

    def acquire(self, tokens: int = 1, max_wait: float = 120.0) -> bool:
        """Block until one request (and `tokens` token-count) is available.

        Returns True on success, False if it had to wait longer than max_wait.
        """
        deadline = time.monotonic() + max(0.0, float(max_wait))
        need_tokens = max(1, int(tokens))

        while True:
            with self._lock:
                self._refill()

                # Daily cap check.
                if self.rpd and self._day_used >= self.rpd:
                    # Sleep at most until deadline; day window won't reset
                    # mid-run in practice, but still honor max_wait.
                    pass
                else:
                    req_ok = self._tokens_req >= 1.0
                    tok_ok = (not self.tpm) or self._tokens_tok >= need_tokens
                    if req_ok and tok_ok:
                        self._tokens_req -= 1.0
                        if self.tpm:
                            self._tokens_tok -= need_tokens
                        self._day_used += 1
                        return True

                # Compute sleep time to next viable moment.
                wait_req = (1.0 - self._tokens_req) / self._rate_req if self._tokens_req < 1.0 else 0.0
                wait_tok = 0.0
                if self.tpm and self._tokens_tok < need_tokens:
                    wait_tok = (need_tokens - self._tokens_tok) / self._rate_tok if self._rate_tok > 0 else 0.0
                sleep_for = max(wait_req, wait_tok, 0.05)

            now = time.monotonic()
            if now >= deadline:
                return False
            sleep_for = min(sleep_for, max(0.0, deadline - now))
            if sleep_for <= 0:
                return False
            time.sleep(sleep_for)

    def snapshot(self) -> dict:
        """Return current state for diagnostics."""
        with self._lock:
            self._refill()
            return {
                "rpm": self.rpm,
                "tpm": self.tpm,
                "rpd": self.rpd,
                "req_available": round(self._tokens_req, 2),
                "tok_available": round(self._tokens_tok, 2) if self.tpm else None,
                "day_used": self._day_used,
            }


# Retry policy constants (also used by tests).
RETRY_DELAYS = [0.0, 5.0, 15.0, 45.0]  # attempts 1..4
MAX_RETRIES = len(RETRY_DELAYS)


def compute_retry_delay(attempt: int, retry_after: Optional[float] = None) -> float:
    """Return delay before `attempt` (1-indexed). Honors Retry-After if given."""
    if retry_after is not None and retry_after >= 0:
        return float(retry_after)
    if attempt < 1:
        return 0.0
    idx = min(attempt - 1, len(RETRY_DELAYS) - 1)
    return RETRY_DELAYS[idx]
