"""Captions document — the Phase 1 → Phase 2 handoff format."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
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
class CaptionsDoc:
    source_clips: list[str]
    edl: list[EdlEntry]
    words: list[CaptionWord]


def save_captions_doc(doc: CaptionsDoc, path: Path) -> None:
    data = {
        "source_clips": doc.source_clips,
        "edl": [asdict(e) for e in doc.edl],
        "words": [asdict(w) for w in doc.words],
    }
    path.write_text(json.dumps(data, indent=2))


def load_captions_doc(path: Path) -> CaptionsDoc:
    raw = json.loads(path.read_text())
    return CaptionsDoc(
        source_clips=raw.get("source_clips", []),
        edl=[EdlEntry(**e) for e in raw.get("edl", [])],
        words=[CaptionWord(**w) for w in raw.get("words", [])],
    )
