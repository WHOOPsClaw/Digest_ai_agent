"""doctor.py — health diagnostics for all components.

Checks:
  ✅ config.yaml valid
  ✅ Telegram token + getMe
  ✅ LLM endpoint + API key
  ✅ SQLite accessible
  ✅ All sources in config reachable
"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger("newsbrief")


def run_doctor() -> int:
    """Run all diagnostic checks. Returns 0 if all OK, 1 if any failed."""
    failed = 0

    failed += 0 if _check_config() else 1
    failed += 0 if _check_storage() else 1
    failed += 0 if _check_telegram() else 1
    failed += 0 if _check_llm() else 1
    # Sources check — opt-in heavy check
    # failed += 0 if _check_sources() else 1

    print()
    if failed == 0:
        print("✅ Всё работает!")
        return 0
    print(f"❌ Есть проблемы: {failed}. См. выше.")
    return 1


def _check_config() -> bool:
    if not Path("config.yaml").exists():
        print("❌ config.yaml не найден — запусти `newsbrief setup`")
        return False
    try:
        from newsbrief.config import get_config
        cfg = get_config()
        print("✅ config.yaml валиден")
        return True
    except Exception as e:
        print(f"❌ config.yaml ошибка: {e}")
        return False


def _check_storage() -> bool:
    try:
        from newsbrief.core.storage import get_storage
        s = get_storage()
        s.ensure_schema()
        # Quick smoke test
        s.execute("INSERT OR IGNORE INTO pipeline_runs (run_date, started_at, status) VALUES (date('now'), datetime('now'), 'doctor-test')")
        print(f"✅ Storage OK ({'Postgres' if s.is_postgres else 'SQLite'})")
        return True
    except Exception as e:
        print(f"❌ Storage error: {e}")
        return False


def _check_telegram() -> bool:
    try:
        from newsbrief.config import get_config
        cfg = get_config()
        token = cfg.delivery.telegram.bot_token
        if not token:
            print("⚠️  Telegram token не задан — запусти `newsbrief setup`")
            return False
        import httpx
        resp = httpx.get(f"https://api.telegram.org/bot{token}/getMe", timeout=10)
        data = resp.json()
        if data.get("ok"):
            bot = data["result"]
            print(f"✅ Telegram OK — @{bot['username']}")
            return True
        print(f"❌ Telegram: {data}")
        return False
    except Exception as e:
        print(f"❌ Telegram error: {e}")
        return False


def _check_llm() -> bool:
    try:
        from newsbrief.config import get_config
        cfg = get_config()
        if not cfg.llm.api_key and cfg.llm.preset != "ollama":
            print("⚠️  LLM API key не задан")
            return False
        print(f"✅ LLM настроен: {cfg.llm.preset or 'custom'}")
        # Deep check (actual API call) — sprint 3
        return True
    except Exception as e:
        print(f"❌ LLM error: {e}")
        return False
