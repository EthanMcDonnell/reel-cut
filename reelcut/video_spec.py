"""Video sidecar — one entry per rendered `.mp4`, in `assets/<slug>/videos.json`.

This is the single hand-authored description of what comes out of a render (filled in by
`/produce-video`). Each entry carries everything that makes one video distinct:

* `id`      — stable handle for the entry; also the last-resort filename
* `title` / `subtitle` / `scrim` — the burned-in title card
* `start` / `end` — the hook window on the **output timeline** (base entries only)
* `caption`  — the Instagram/Telegram post text
* `filename` — filesystem stem for the `.mp4`
* `of`       — set on a mirrored duplicate: the `id` of the entry it mirrors

A base entry (no `of`) defines one hook. An entry with `of` is that hook rendered a second
time with the footage flipped (`output.flip.apply: duplicate`) — it gets its own card, its
own caption and its own filename, so the copy shares no text with the original. It inherits
the base entry's hook window; `start`/`end` on a duplicate are ignored.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class VideoSpec:
    id: str
    title: str = ""            # burned-in card title; "\n" for explicit line breaks
    subtitle: str = ""
    scrim: bool | None = None  # None → use config default
    start: float = 0.0         # output-timeline seconds (base entries)
    end: float = 0.0
    caption: str = ""          # pretty post text, e.g. "why reddit ditched kafka 😵"
    filename: str = ""         # filesystem stem, e.g. "why-reddit-ditched-kafka"
    of: str = ""               # base entry id this one mirrors ("" → this IS a base entry)


def load_videos(path: Path) -> list[VideoSpec]:
    """Load videos.json (a JSON list). Returns [] if the file is missing or the stub is empty.

    Rejects duplicate ids and an `of` that names no base entry — both are authoring slips
    that would otherwise surface as a mis-titled or silently unrendered video.
    """
    path = Path(path)
    if not path.exists():
        return []
    raw = json.loads(path.read_text())
    if not isinstance(raw, list):
        raise ValueError(f"{path} must be a JSON list of video objects")

    videos = [
        VideoSpec(
            id=v.get("id", ""),
            title=v.get("title", ""),
            subtitle=v.get("subtitle", ""),
            scrim=v.get("scrim"),
            start=float(v.get("start", 0.0)),
            end=float(v.get("end", 0.0)),
            caption=v.get("caption", ""),
            filename=v.get("filename", ""),
            of=v.get("of", ""),
        )
        for v in raw
    ]

    ids = [v.id for v in videos]
    if "" in ids:
        raise ValueError(f"{path}: every entry needs an id")
    if len(set(ids)) != len(ids):
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        raise ValueError(f"{path}: duplicate entry id(s): {', '.join(dupes)}")
    base_ids = {v.id for v in videos if not v.of}
    for v in videos:
        if v.of and v.of not in base_ids:
            raise ValueError(f"{path}: entry {v.id!r} mirrors {v.of!r}, which is not an entry")
    return videos


def base_videos(videos: list[VideoSpec]) -> list[VideoSpec]:
    """The hook-defining entries, in file order — one per hook window."""
    return [v for v in videos if not v.of]


def mirror_of(videos: list[VideoSpec], base_id: str) -> VideoSpec | None:
    """The entry that mirrors `base_id`, or None when the duplicate isn't described."""
    return next((v for v in videos if v.of == base_id), None)


def stem_for(video: VideoSpec) -> str:
    """Filesystem stem for this entry's `.mp4`: its filename, else its caption, else its id."""
    return safe_slug(video.filename) or safe_slug(video.caption) or safe_slug(video.id)


def safe_slug(text: str) -> str:
    """Reduce a title (or authored filename) to a filesystem/URL-safe stem: lowercase ASCII
    words joined by single hyphens, with emoji and punctuation dropped. Returns "" if nothing
    usable survives (caller falls back to the next candidate)."""
    ascii_only = text.encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "-", ascii_only).strip("-")
