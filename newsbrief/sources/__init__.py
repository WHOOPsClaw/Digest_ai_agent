"""Source adapters for newsbrief."""
from newsbrief.sources.base import (
    SourceProvider,
    register,
    get_provider,
    all_providers,
    load_plugins,
)
from newsbrief.sources.rss import RSSProvider
from newsbrief.sources.telegram import TelegramProvider
from newsbrief.sources.reddit import RedditProvider
from newsbrief.sources.hackernews import HackerNewsProvider
from newsbrief.sources.youtube import YouTubeProvider
from newsbrief.sources.search import SearchProvider

# Auto-register built-in providers
for _p in (
    RSSProvider(),
    TelegramProvider(),
    RedditProvider(),
    HackerNewsProvider(),
    YouTubeProvider(),
    SearchProvider(),
):
    register(_p)

__all__ = [
    "SourceProvider",
    "RSSProvider",
    "TelegramProvider",
    "RedditProvider",
    "HackerNewsProvider",
    "YouTubeProvider",
    "SearchProvider",
    "register",
    "get_provider",
    "all_providers",
    "load_plugins",
]


def fetch_all(config, parallel_workers: int = 6):
    """Fetch all articles from all topics in config.

    Returns dict[category_id] -> list[RawArticle].
    Uses ThreadPoolExecutor for parallel fetching.
    """
    import logging
    from concurrent.futures import ThreadPoolExecutor, as_completed

    logger = logging.getLogger("newsbrief.fetcher")

    def _fetch_topic(topic):
        articles = []
        cat = topic.id

        # RSS
        rss_cfgs = (topic.sources or {}).get("rss", [])
        for rss_cfg in rss_cfgs:
            if isinstance(rss_cfg, str):
                rss_cfg = {"url": rss_cfg}
            rss_cfg = {**rss_cfg, "category": cat}
            try:
                articles.extend(list(RSSProvider().fetch(rss_cfg, limit=10)))
            except Exception as e:
                logger.warning("rss failed: %s", e)

        # Telegram
        tg_cfgs = (topic.sources or {}).get("telegram", [])
        for tg_cfg in tg_cfgs:
            if isinstance(tg_cfg, str):
                tg_cfg = {"username": tg_cfg}
            tg_cfg = {**tg_cfg, "category": cat}
            try:
                articles.extend(list(TelegramProvider().fetch(tg_cfg, limit=15)))
            except Exception as e:
                logger.warning("tg failed: %s", e)

        # Reddit
        reddit_cfgs = (topic.sources or {}).get("reddit", [])
        for r_cfg in reddit_cfgs:
            if isinstance(r_cfg, str):
                r_cfg = {"sub": r_cfg}
            r_cfg = {**r_cfg, "category": cat}
            try:
                articles.extend(list(RedditProvider().fetch(r_cfg, limit=15)))
            except Exception as e:
                logger.warning("reddit failed: %s", e)

        # HackerNews
        hn_cfg = (topic.sources or {}).get("hackernews")
        if hn_cfg:
            if hn_cfg is True:
                hn_cfg = {}
            hn_cfg = {**(hn_cfg if isinstance(hn_cfg, dict) else {}), "category": cat}
            try:
                articles.extend(list(HackerNewsProvider().fetch(hn_cfg, limit=15)))
            except Exception as e:
                logger.warning("hn failed: %s", e)

        # YouTube
        yt_cfgs = (topic.sources or {}).get("youtube", [])
        for yt_cfg in yt_cfgs:
            if isinstance(yt_cfg, str):
                yt_cfg = {"channel_id": yt_cfg}
            yt_cfg = {**yt_cfg, "category": cat}
            try:
                articles.extend(list(YouTubeProvider().fetch(yt_cfg, limit=10)))
            except Exception as e:
                logger.warning("yt failed: %s", e)

        # Search (not auto - user must specify)
        search_cfgs = (topic.sources or {}).get("search", [])
        for s_cfg in search_cfgs:
            if isinstance(s_cfg, str):
                s_cfg = {"query": s_cfg}
            s_cfg = {**s_cfg, "category": cat}
            try:
                articles.extend(list(SearchProvider().fetch(s_cfg, limit=5)))
            except Exception as e:
                logger.warning("search failed: %s", e)

        # Deduplicate by URL within topic
        seen = set()
        result = []
        for a in articles:
            if a.url not in seen:
                seen.add(a.url)
                result.append(a)

        logger.info("fetcher: topic=%s articles=%d", cat, len(result))
        return cat, result

    topics = config.topics or []
    results = {}
    with ThreadPoolExecutor(max_workers=min(parallel_workers, max(1, len(topics)))) as pool:
        futures = {pool.submit(_fetch_topic, t): t for t in topics}
        for fut in as_completed(futures):
            try:
                cat, articles = fut.result()
                results[cat] = articles
            except Exception as e:
                logger.error("topic fetch failed: %s", e)

    return results


__all__.append("fetch_all")
