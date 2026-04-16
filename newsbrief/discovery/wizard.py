"""Interactive CLI wizard for source discovery."""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

try:
    import questionary
except ImportError:  # pragma: no cover
    questionary = None

from newsbrief.discovery import load_known_sources
from newsbrief.discovery.matcher import match_interests
from newsbrief.discovery.validator import validate_source
from newsbrief.discovery.yaml_gen import generate_topics_yaml, source_id

logger = logging.getLogger(__name__)


def _source_label(src: dict[str, Any]) -> str:
    stype = src.get("type") or "?"
    name = src.get("name") or ""
    cfg = src.get("config") or {}
    if stype == "rss":
        tail = src.get("url", "")[:60]
    elif stype == "telegram":
        tail = f"@{cfg.get('username', '')}"
    elif stype == "reddit":
        tail = f"r/{cfg.get('sub', '')}"
    elif stype == "hackernews":
        tail = cfg.get("type", "top")
    else:
        tail = ""
    q = src.get("quality") or ""
    q_tag = f" [{q}]" if q else ""
    return f"[{stype}] {name} — {tail}{q_tag}"


def run_discovery_wizard(config: Any, llm_router: Any) -> list[dict[str, Any]]:
    """Run interactive discovery. Returns list of TopicConfig dicts."""
    if questionary is None:
        print("ERROR: questionary not installed. Run: pip install questionary")
        return []

    # Step 1: interests
    interests_default = getattr(getattr(config, "user", None), "profile", "") or ""
    if interests_default:
        print(f"\nТекущие интересы: {interests_default[:150]}")
    interests = questionary.text(
        "Опиши интересы (можно в несколько строк):",
        multiline=True,
        default=interests_default,
    ).ask()
    if not interests:
        print("Без интересов не могу ничего подобрать. Выход.")
        return []

    # Step 2: match
    print("\n🔍 Подбираю темы и источники...")
    known = load_known_sources()
    matched = match_interests(interests, llm_router, known)
    if not matched:
        print("Не удалось подобрать темы. Проверь LLM/ключ.")
        return []

    # Step 3: for each topic, let user pick sources
    selected_ids: set[str] = set()
    for topic in matched:
        print(
            f"\n{topic['emoji']} {topic['display_name']} — {topic.get('reasoning', '')}"
        )
        choices = []
        for entry in topic.get("sources", []):
            src = entry["source_ref"]
            choices.append(
                questionary.Choice(
                    title=_source_label(src),
                    value=source_id(src),
                    checked=bool(entry.get("recommended")),
                )
            )
        if not choices:
            continue
        picked = questionary.checkbox(
            f"Выбери источники для темы {topic['display_name']}:",
            choices=choices,
        ).ask()
        if picked:
            selected_ids.update(picked)

    if not selected_ids:
        print("Ничего не выбрано.")
        return []

    # Step 4: validate selected sources in parallel
    print("\n🔎 Проверяю, что источники живы...")
    to_validate: list[tuple[str, dict[str, Any]]] = []
    for topic in matched:
        for entry in topic.get("sources", []):
            src = entry["source_ref"]
            sid = source_id(src)
            if sid in selected_ids:
                to_validate.append((sid, src))

    alive_ids: set[str] = set()
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(validate_source, src): (sid, src) for sid, src in to_validate}
        for fut in as_completed(futs):
            sid, src = futs[fut]
            try:
                res = fut.result()
            except Exception as e:
                res = {"valid": False, "error": str(e)}
            status = "✅" if res.get("valid") else "❌"
            print(f"  {status} {_source_label(src)} {res.get('error', '')}")
            if res.get("valid"):
                alive_ids.add(sid)

    if not alive_ids:
        print("Все выбранные источники недоступны. Выход.")
        return []

    # Step 5: generate topics
    topics = generate_topics_yaml(matched, alive_ids)

    # Step 6: optional web search
    try:
        do_more = questionary.confirm(
            "Искать дополнительные источники через web-поиск? (медленно)", default=False
        ).ask()
    except Exception:
        do_more = False
    if do_more:
        from newsbrief.discovery.web_search import discover_rss_for_topic

        extra_topic = questionary.text("Тема для поиска (одна строка):").ask()
        if extra_topic:
            print("🌐 Ищу...")
            extras = discover_rss_for_topic(extra_topic, llm_router)
            if extras:
                print(f"Найдено {len(extras)} фидов:")
                for e in extras:
                    print(f"  + {e['url']}")
                if topics:
                    topics[0].setdefault("sources", {}).setdefault("rss", [])
                    for e in extras:
                        if e["url"] not in topics[0]["sources"]["rss"]:
                            topics[0]["sources"]["rss"].append(e["url"])
            else:
                print("Ничего не найдено.")

    print(f"\n✅ Готово: {len(topics)} тем.")
    return topics
