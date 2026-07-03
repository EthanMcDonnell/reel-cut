"""Background audio cues — hand/LLM-authored music/SFX tracks stored in `audio.json`.

Audio lives in `assets/<slug>/audio.json` (a JSON list), separate from captions.json.
Each entry usually just names a `track` from the config audio.library; that entry carries
the file path and its source_start. `start`/`end` are in **output-timeline seconds** (the
final rendered video's timeline, same as headings) and the track is mixed under the voice at
render time. `end = -1` means "until the end of the video"; any audio that runs past the end
of the video is cut.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class AudioSpec:
    """A background audio track's use in one video — mixed under the voice.

    The track is auto-leveled to sit a fixed amount below the voice (config
    audio.ducking_lufs), so the source file's mastering level doesn't matter.

    track:        library key from config audio.library; resolves path + source_start + gain_db
    path:         raw file override, used instead of `track` (empty → use `track`)
    source_start: seconds into the source file to begin (only used with a raw `path`;
                  a library `track` carries its own source_start)
    start:        output-timeline second the track begins (default 0 = start of video)
    end:          output-timeline second the track ends; -1 = until the end of the video
    gain_db:      manual trim in dB on top of the auto-level (added to a library track's own gain_db)
    """
    track: str = ""
    path: str = ""
    source_start: float = 0.0
    start: float = 0.0
    end: float = -1.0
    gain_db: float = 0.0


def load_audio(path: Path) -> list[AudioSpec]:
    """Load audio.json (a JSON list of track objects). Missing file → []. Missing keys tolerated."""
    path = Path(path)
    if not path.exists():
        return []
    raw = json.loads(path.read_text())
    if not isinstance(raw, list):
        raise ValueError(f"{path} must be a JSON list of audio track objects")
    return [
        AudioSpec(
            track=a.get("track", ""),
            path=a.get("path", ""),
            source_start=float(a.get("source_start", 0.0)),
            start=float(a.get("start", 0.0)),
            end=float(a.get("end", -1.0)),
            gain_db=float(a.get("gain_db", 0.0)),
        )
        for a in raw
    ]


def save_audio(tracks: list[AudioSpec], path: Path) -> None:
    Path(path).write_text(json.dumps([asdict(a) for a in tracks], indent=2) + "\n")
