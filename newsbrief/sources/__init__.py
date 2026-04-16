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
