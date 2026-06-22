"""Image overlays — hand/LLM-authored image cues stored in `images.json`.

Images live in `assets/<slug>/images.json` (a JSON list), separate from captions.json.
Unlike headings (output-timeline), image `start`/`end` are in **source-clip time** — the
same timeline as `words`/`edl` — and are remapped to the output timeline at render time.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class ImageSpec:
    """LLM-populated image overlay. Edit start/end to control when it appears.

    type: "person"     — name is a Wikipedia person name; image fetched automatically
    type: "screenshot" — path points to a local image file
    type: "concept"    — name is a concept keyword from concepts.yaml (bug, handcuffs, …),
                         resolved to a sticker/emoji automatically
    """
    type: str               # "person" | "screenshot" | "concept"
    start: float            # source-clip seconds (same timeline as words/edl)
    end: float              # source-clip seconds (remapped to output-timeline at render time)
    source_clip: str = ""   # path to source clip — copy from the words the image is anchored to
    name: str = ""          # person full name (type=person) or concept keyword (type=concept)
    path: str = ""          # absolute path to screenshot PNG/JPG


def load_images(path: Path) -> list[ImageSpec]:
    """Load images.json (a JSON list of image objects). Missing file → []. Missing keys tolerated."""
    path = Path(path)
    if not path.exists():
        return []
    raw = json.loads(path.read_text())
    if not isinstance(raw, list):
        raise ValueError(f"{path} must be a JSON list of image objects")
    return [
        ImageSpec(
            type=i.get("type", ""),
            start=float(i.get("start", 0.0)),
            end=float(i.get("end", 0.0)),
            source_clip=i.get("source_clip", ""),
            name=i.get("name", ""),
            path=i.get("path", ""),
        )
        for i in raw
    ]


def save_images(images: list[ImageSpec], path: Path) -> None:
    Path(path).write_text(json.dumps([asdict(i) for i in images], indent=2) + "\n")
