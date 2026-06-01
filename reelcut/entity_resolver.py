"""Wikipedia image resolver — fetches a thumbnail for a named entity and caches it locally."""
from __future__ import annotations

import hashlib
import json
import pathlib
import urllib.parse
import urllib.request

_CACHE_DIR = pathlib.Path.home() / ".cache" / "reelcut" / "entity_images"
_WIKI_API = "https://en.wikipedia.org/w/api.php"
_HEADERS = {"User-Agent": "reelcut/1.0"}


def resolve_entity_image(name: str, entity_type: str) -> pathlib.Path | None:
    """Return a cached PNG path for *name*, or None if not found."""
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_key = hashlib.md5(name.lower().encode()).hexdigest()
    cached = _CACHE_DIR / f"{cache_key}.png"
    if cached.exists():
        return cached

    url = _thumbnail_url(name)
    if url is None:
        return None

    try:
        req = urllib.request.Request(url, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=10) as resp:
            cached.write_bytes(resp.read())
        return cached
    except Exception:
        return None


def _thumbnail_url(name: str) -> str | None:
    """Query Wikipedia API for the page thumbnail URL of *name*."""
    params = urllib.parse.urlencode({
        "action": "query",
        "titles": name,
        "prop": "pageimages",
        "pithumbsize": 400,
        "format": "json",
        "redirects": 1,
    })
    try:
        req = urllib.request.Request(f"{_WIKI_API}?{params}", headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        pages = data.get("query", {}).get("pages", {})
        for page in pages.values():
            thumb = page.get("thumbnail", {})
            if thumb.get("source"):
                return thumb["source"]
    except Exception:
        pass
    return None
