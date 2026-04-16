"""core/scheduler.py — smart scheduler with adaptive build-time buffer.

Two daily jobs:
  - build: at calculated build_at (send_at − buffer)
  - send:  at config.schedule.send_at

Buffer policy:
  1. If config.schedule.build_buffer_minutes set → use that (override).
  2. Else if ≥7 pipeline_runs recorded → rolling_avg × 1.3.
  3. Else → BUFFER_DEFAULTS[llm_preset].
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Callable, Optional
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger("newsbrief")

# Default build-time buffers per provider (minutes)
BUFFER_DEFAULTS = {
    "groq":       15,
    "cerebras":   15,
    "gemini":     20,
    "mistral":    20,
    "openai":     30,
    "anthropic":  30,
    "openrouter": 30,
    "deepseek":   40,
}

BUFFER_MIN = 5
BUFFER_MAX = 120
ROLLING_MULTIPLIER = 1.3
ROLLING_MIN_SAMPLES = 7
ROLLING_WINDOW_DAYS = 7
CHANGE_NOTIFY_THRESHOLD_MIN = 5


# ---------------------------------------------------------------------------
# Time math
# ---------------------------------------------------------------------------

def _parse_hhmm(s: str) -> tuple[int, int]:
    hh, mm = s.strip().split(":")
    return int(hh), int(mm)


def _fmt_hhmm(h: int, m: int) -> str:
    return f"{h:02d}:{m:02d}"


def _subtract_minutes(send_at: str, minutes: int) -> str:
    h, m = _parse_hhmm(send_at)
    total = h * 60 + m - minutes
    total %= 24 * 60  # wrap (allow previous-day build)
    return _fmt_hhmm(total // 60, total % 60)


# ---------------------------------------------------------------------------
# Rolling average from storage
# ---------------------------------------------------------------------------

def _rolling_avg_minutes(storage) -> Optional[float]:
    """Return rolling avg pipeline duration (minutes) over last N runs, or None."""
    if storage is None:
        return None
    try:
        rows = storage.fetchall(
            "SELECT duration_sec FROM pipeline_runs "
            "WHERE status = 'ok' AND duration_sec IS NOT NULL "
            "ORDER BY started_at DESC LIMIT %s",
            (ROLLING_MIN_SAMPLES * 2,),
        )
    except Exception as e:
        logger.warning("[scheduler] rolling avg query failed: %s", e)
        return None

    durations = [float(r["duration_sec"]) for r in rows if r.get("duration_sec")]
    if len(durations) < ROLLING_MIN_SAMPLES:
        return None
    avg_sec = sum(durations[:ROLLING_MIN_SAMPLES]) / ROLLING_MIN_SAMPLES
    return avg_sec / 60.0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def calculate_build_time(
    send_at: str,
    llm_preset: Optional[str] = "groq",
    override_buffer: Optional[int] = None,
    storage=None,
) -> str:
    """Return build_at (HH:MM) given send_at and buffer strategy."""
    buffer = calculate_buffer_minutes(llm_preset, override_buffer, storage)
    return _subtract_minutes(send_at, buffer)


def calculate_buffer_minutes(
    llm_preset: Optional[str] = "groq",
    override_buffer: Optional[int] = None,
    storage=None,
) -> int:
    if override_buffer is not None:
        return max(BUFFER_MIN, min(BUFFER_MAX, int(override_buffer)))

    avg_min = _rolling_avg_minutes(storage)
    if avg_min is not None:
        buf = int(round(avg_min * ROLLING_MULTIPLIER))
        return max(BUFFER_MIN, min(BUFFER_MAX, buf))

    preset = (llm_preset or "groq").lower()
    return BUFFER_DEFAULTS.get(preset, 30)


def update_buffer_from_history(storage, current_buffer: int = 0) -> int:
    """Called after a pipeline run. Returns recommended buffer minutes.

    If it differs from `current_buffer` by > CHANGE_NOTIFY_THRESHOLD_MIN, logs.
    """
    new_buf = calculate_buffer_minutes(storage=storage)
    if abs(new_buf - current_buffer) > CHANGE_NOTIFY_THRESHOLD_MIN:
        logger.info(
            "[scheduler] adaptive buffer change: %d → %d min (rolling avg)",
            current_buffer, new_buf,
        )
    return new_buf


# ---------------------------------------------------------------------------
# Scheduler construction
# ---------------------------------------------------------------------------

def build_scheduler(
    config,
    on_build: Callable[[], None],
    on_send:  Callable[[], None],
    storage=None,
) -> BackgroundScheduler:
    """Build & configure APScheduler. Caller is responsible for .start()."""
    tz_name = config.schedule.timezone or "Europe/Moscow"
    tz      = ZoneInfo(tz_name)
    sched   = BackgroundScheduler(timezone=tz)

    send_at = config.schedule.send_at or "09:00"
    build_at = config.schedule.build_at or calculate_build_time(
        send_at=send_at,
        llm_preset=config.llm.preset,
        override_buffer=config.schedule.build_buffer_minutes,
        storage=storage,
    )

    b_h, b_m = _parse_hhmm(build_at)
    s_h, s_m = _parse_hhmm(send_at)

    def _send_wrapped():
        # Honor pause state — skip sending while paused_until > now.
        try:
            from newsbrief.core.pause import is_paused, get_paused_until
            if is_paused(storage):
                until = get_paused_until(storage)
                logger.info("[scheduler] skipped (paused until %s)", until)
                return
        except Exception as e:
            logger.warning("[scheduler] pause check failed: %s", e)
        on_send()

    sched.add_job(
        on_build,
        trigger=CronTrigger(hour=b_h, minute=b_m, timezone=tz),
        id="nb_build",
        name=f"newsbrief BUILD {build_at} {tz_name}",
        max_instances=1, coalesce=True, replace_existing=True,
    )
    sched.add_job(
        _send_wrapped,
        trigger=CronTrigger(hour=s_h, minute=s_m, timezone=tz),
        id="nb_send",
        name=f"newsbrief SEND {send_at} {tz_name}",
        max_instances=1, coalesce=True, replace_existing=True,
    )

    logger.info(
        "[scheduler] configured: build=%s send=%s tz=%s",
        build_at, send_at, tz_name,
    )
    return sched


# ---------------------------------------------------------------------------
# Blocks scheduler (multi-schedule interest blocks)
# ---------------------------------------------------------------------------

_WEEKDAY_MAP = {
    "mon": "mon", "tue": "tue", "wed": "wed", "thu": "thu",
    "fri": "fri", "sat": "sat", "sun": "sun",
}


def _parse_block_time(spec: str) -> tuple[Optional[str], int, int]:
    """Parse "HH:MM" or "mon 09:00" → (day_of_week|None, hour, minute)."""
    s = (spec or "").strip().lower()
    parts = s.split()
    if len(parts) == 2:
        day = _WEEKDAY_MAP.get(parts[0][:3])
        h, m = _parse_hhmm(parts[1])
        return day, h, m
    h, m = _parse_hhmm(s)
    return None, h, m


def build_blocks_scheduler(
    config,
    on_block: Callable[[object], None],
    storage=None,
) -> BackgroundScheduler:
    """Build a scheduler with one job per config.blocks entry.

    `on_block` is called with the BlockConfig instance when its trigger fires.
    Returns a scheduler with no jobs when config.blocks is empty.
    """
    tz_name = config.schedule.timezone or "Europe/Moscow"
    tz      = ZoneInfo(tz_name)
    sched   = BackgroundScheduler(timezone=tz)

    for idx, block in enumerate(getattr(config, "blocks", []) or []):
        try:
            dow, h, m = _parse_block_time(block.time)
        except Exception as e:
            logger.warning("[scheduler] skip block %r: bad time %r (%s)",
                           block.name, block.time, e)
            continue
        trigger_kwargs: dict = {"hour": h, "minute": m, "timezone": tz}
        if dow:
            trigger_kwargs["day_of_week"] = dow
        sched.add_job(
            on_block,
            trigger=CronTrigger(**trigger_kwargs),
            args=[block],
            id=f"nb_block_{idx}_{block.name}",
            name=f"newsbrief BLOCK {block.name} {block.time} {tz_name}",
            max_instances=1, coalesce=True, replace_existing=True,
        )
        logger.info("[scheduler] block job: %s @ %s tz=%s",
                    block.name, block.time, tz_name)

    return sched
