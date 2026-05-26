"""Logo resolver — downloads SVGs from gilbarbara/logos and converts to PNG via cairosvg."""
from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path

_MANIFEST_URL = "https://raw.githubusercontent.com/gilbarbara/logos/main/logos.json"
_RAW_BASE = "https://raw.githubusercontent.com/gilbarbara/logos/main/logos"
_CACHE_DIR = Path.home() / ".cache" / "reelcut" / "logos"


def _cache_dir() -> Path:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return _CACHE_DIR


def load_manifest() -> dict[str, list[str]]:
    """Return {shortname: [filename, ...]} from the cached gilbarbara/logos manifest.

    Downloads logos.json on first call and caches it permanently at
    ~/.cache/reelcut/logos/logos.json. Delete that file to force a refresh.
    """
    path = _cache_dir() / "logos.json"
    if not path.exists():
        try:
            with urllib.request.urlopen(_MANIFEST_URL, timeout=15) as r:
                path.write_bytes(r.read())
        except Exception as exc:
            raise RuntimeError(
                f"Failed to download logos manifest: {exc}\n"
                "Check your internet connection, or delete ~/.cache/reelcut/logos/ to reset."
            ) from exc
    return {e["shortname"]: e["files"] for e in json.loads(path.read_text())}


def normalize_slug(word: str) -> str:
    """Normalize a transcript word to a logos shortname slug."""
    slug = word.lower().replace(" ", "-").replace("_", "-")
    slug = re.sub(r"[^a-z0-9-]", "", slug)
    return slug.strip("-")


def resolve_logo(slug: str, manifest: dict[str, list[str]]) -> Path | None:
    """Resolve a shortname slug to a local PNG path. Returns None if unavailable."""
    files = manifest.get(slug)
    if not files:
        return None
    icon_files = [f for f in files if "-icon" in f]
    chosen = icon_files[0] if icon_files else files[0]
    return _ensure_png(chosen)


def _ensure_png(filename: str) -> Path | None:
    """Download SVG if not cached, convert to PNG, return PNG path. Returns None on error."""
    cache = _cache_dir()
    png_path = cache / (Path(filename).stem + ".png")
    if png_path.exists():
        return png_path

    svg_path = cache / filename
    if not svg_path.exists():
        try:
            with urllib.request.urlopen(f"{_RAW_BASE}/{filename}", timeout=10) as r:
                svg_path.write_bytes(r.read())
        except Exception:
            return None

    try:
        import cairosvg  # type: ignore[import]
    except ImportError:
        raise ImportError(
            "cairosvg is required for auto-image overlays. "
            "Install it with: pip install cairosvg\n"
            "(macOS may also need: brew install cairo)"
        )

    try:
        cairosvg.svg2png(url=str(svg_path), write_to=str(png_path))
        return png_path
    except Exception:
        return None
