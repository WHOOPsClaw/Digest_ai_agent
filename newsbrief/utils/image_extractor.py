"""Extract image URLs from articles."""
from __future__ import annotations

import re
from typing import Optional

_IMG_RE = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE)
_OG_RE = re.compile(
    r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
    re.IGNORECASE,
)

_IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif")


def is_valid_image_url(url: Optional[str]) -> bool:
    if not url:
        return False
    if not isinstance(url, str):
        return False
    u = url.lower().split("?")[0]
    if not (u.startswith("http://") or u.startswith("https://")):
        return False
    if any(u.endswith(ext) for ext in _IMAGE_EXTS):
        return True
    if any(k in u for k in ["/image", "/media/", "/uploads/", "/content/", "/wp-content/"]):
        return True
    return False


def extract_image_from_feedparser_entry(entry) -> Optional[str]:
    """Extract image from feedparser RSS entry."""
    # 1. media_thumbnail
    thumbs = getattr(entry, "media_thumbnail", None)
    if thumbs:
        try:
            url = thumbs[0].get("url")
            if is_valid_image_url(url):
                return url
        except Exception:
            pass
    # 2. media_content
    mcs = getattr(entry, "media_content", None)
    if mcs:
        for mc in mcs:
            try:
                if mc.get("medium") == "image" or "image" in (mc.get("type") or ""):
                    url = mc.get("url")
                    if is_valid_image_url(url):
                        return url
            except Exception:
                continue
    # 3. enclosures
    encs = getattr(entry, "enclosures", None)
    if encs:
        for enc in encs:
            try:
                if "image" in (enc.get("type") or ""):
                    url = enc.get("href") or enc.get("url")
                    if is_valid_image_url(url):
                        return url
            except Exception:
                continue
    # 4. <img> in summary/description
    for field in ("summary", "description"):
        raw = getattr(entry, field, "") or ""
        if raw:
            m = _IMG_RE.search(raw)
            if m and is_valid_image_url(m.group(1)):
                return m.group(1)
    content = getattr(entry, "content", None)
    if content:
        for c in content:
            try:
                val = c.get("value", "") or ""
            except Exception:
                val = ""
            m = _IMG_RE.search(val)
            if m and is_valid_image_url(m.group(1)):
                return m.group(1)
    return None


def extract_image_from_reddit(post: dict) -> Optional[str]:
    """Extract image from a Reddit JSON post's data dict."""
    if not isinstance(post, dict):
        return None
    preview = post.get("preview") or {}
    images = preview.get("images") or []
    if images:
        try:
            url = images[0].get("source", {}).get("url")
            if url:
                url = url.replace("&amp;", "&")
                if is_valid_image_url(url):
                    return url
        except Exception:
            pass
    thumb = post.get("thumbnail", "") or ""
    if thumb not in ("self", "default", "nsfw", "spoiler", "") and is_valid_image_url(thumb):
        return thumb
    post_url = post.get("url", "") or ""
    if is_valid_image_url(post_url) and any(
        post_url.lower().split("?")[0].endswith(e) for e in _IMAGE_EXTS
    ):
        return post_url
    return None


def extract_image_from_html(html: str) -> Optional[str]:
    """Extract og:image or first <img> from HTML."""
    if not html:
        return None
    m = _OG_RE.search(html)
    if m and is_valid_image_url(m.group(1)):
        return m.group(1)
    m = _IMG_RE.search(html)
    if m and is_valid_image_url(m.group(1)):
        return m.group(1)
    return None
