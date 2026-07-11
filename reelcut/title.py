"""Instagram title sidecar — the viewer-facing title for each per-hook video.

Titles are authored in `assets/<slug>/title.json` (a list, one entry per hook, parallel to
headings.json). Each entry carries a `title` (the pretty, lowercase, one-emoji caption used in
the Telegram/Instagram post) and a `slug` (a filesystem-safe form used to name the rendered
`output/<slug>/<title-slug>.mp4`). Unlike headings, nothing here is rendered into the video —
it only names the file and captions the post.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class TitleSpec:
    title: str  # pretty caption, e.g. "reddit & kafka -> kubernetes w/ no 🧑❓"
    slug: str = ""  # filesystem-safe stem, e.g. "reddit-kafka-to-kubernetes"


def load_titles(path: Path) -> list[TitleSpec]:
    """Load title.json (a JSON list). Returns [] if the file is missing or the stub is empty."""
    path = Path(path)
    if not path.exists():
        return []
    raw = json.loads(path.read_text())
    if not isinstance(raw, list):
        raise ValueError(f"{path} must be a JSON list of title objects")
    return [TitleSpec(title=t.get("title", ""), slug=t.get("slug", "")) for t in raw]


def safe_slug(text: str) -> str:
    """Reduce a title (or authored slug) to a filesystem/URL-safe stem: lowercase ASCII
    words joined by single hyphens, with emoji and punctuation dropped. Returns "" if nothing
    usable survives (caller falls back to a positional name)."""
    ascii_only = text.encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "-", ascii_only).strip("-")
