"""Captions document — the Phase 1 → Phase 2 handoff format."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class CaptionWord:
    word: str
    start: float        # source-clip seconds (WhisperX aligned)
    end: float          # source-clip seconds (WhisperX aligned)
    source_clip: str    # path to source clip this word came from


@dataclass
class EdlEntry:
    source_clip: str
    start: float   # source-clip seconds
    end: float     # source-clip seconds
    keep: bool
    reason: str


@dataclass
class ImageSpec:
    """LLM-populated image overlay. Edit start/end to control when it appears.

    type: "person"     — name is a Wikipedia person name; image fetched automatically
    type: "screenshot" — path points to a local image file
    """
    type: str               # "person" | "screenshot"
    start: float            # source-clip seconds (same timeline as words/edl)
    end: float              # source-clip seconds (remapped to output-timeline at render time)
    source_clip: str = ""   # path to source clip — copy from the words the image is anchored to
    name: str = ""          # person full name, e.g. "Sam Altman"
    path: str = ""          # absolute path to screenshot PNG/JPG


@dataclass
class CaptionsDoc:
    source_clips: list[str]
    edl: list[EdlEntry]
    words: list[CaptionWord]
    images: list[ImageSpec] = field(default_factory=list)


def save_captions_doc(doc: CaptionsDoc, path: Path) -> None:
    data = {
        "source_clips": doc.source_clips,
        "edl": [asdict(e) for e in doc.edl],
        "words": [asdict(w) for w in doc.words],
        "images": [asdict(i) for i in doc.images],
    }
    path.write_text(json.dumps(data, indent=2))


def load_captions_doc(path: Path) -> CaptionsDoc:
    raw = json.loads(path.read_text())
    return CaptionsDoc(
        source_clips=raw.get("source_clips", []),
        edl=[EdlEntry(**e) for e in raw.get("edl", [])],
        words=[CaptionWord(**w) for w in raw.get("words", [])],
        images=[ImageSpec(**i) for i in raw.get("images", [])],
    )
