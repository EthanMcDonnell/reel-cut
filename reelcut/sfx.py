"""Sound effects — one short sound on each overlay's first frame.

Events come from the render's own cues (overlay starts, animated-card beats, heading cards),
so nothing is authored per video. Each effect is shifted so its loudest moment lands on the
event's frame — a whoosh builds before its peak, a click peaks at once — and an effect closer
than `sfx.min_gap_s` to the one before is dropped, so a burst of overlays gets one sound.
"""
from __future__ import annotations

from collections import Counter
from functools import lru_cache
from pathlib import Path

from .config import SfxConfig

_SR = 48000
_AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus"}


def sfx_events(cues: list, headings: list) -> list[tuple[str, float, int]]:
    """(event, output-timeline second, index) for every overlay start, card beat and heading.

    An animated card renders as a `video` cue with kind "card", so it fires `card`, not `video`.
    A beat's index is its position in the card; beats past the cue's end (cut off at a hook
    boundary) are skipped.
    """
    events = []
    for c in cues:
        events.append(("card" if c.kind == "card" else c.type, c.start, 0))
        events.extend(("beat", b, i) for i, b in enumerate(c.beats) if b < c.end)
    events.extend(("heading", h.start, 0) for h in headings)
    return events


def sfx_library(sfx_dir: Path) -> dict[str, Path]:
    """Sound files in `sfx_dir`, keyed by file stem."""
    if not sfx_dir.is_dir():
        return {}
    return {p.stem: p for p in sorted(sfx_dir.iterdir()) if p.suffix.lower() in _AUDIO_EXTS}


@lru_cache(maxsize=None)
def analyze(path: str) -> tuple[float, float, float]:
    """(seconds to the peak sample, peak dBFS, duration seconds) of a sound file."""
    import ffmpeg
    import numpy as np

    raw, _ = (
        ffmpeg.input(path)
        .output("-", format="f32le", ac=1, ar=_SR)
        .run(capture_stdout=True, quiet=True)
    )
    x = np.abs(np.frombuffer(raw, np.float32))
    if not len(x) or x.max() <= 0:
        return 0.0, -120.0, len(x) / _SR
    return float(x.argmax()) / _SR, float(20 * np.log10(x.max())), len(x) / _SR


def plan_sfx(
    events: list[tuple[str, float, int]],
    config: SfxConfig,
    library: dict[str, Path],
    total_s: float,
    warnings: list[str],
) -> list[dict]:
    """Renderer-ready track dicts for `events`, peak-aligned and rate-limited.

    Each dict carries `peak_db` and `level_db`, which the renderer's leveling uses to set the
    effect's peak relative to the voice instead of measuring its integrated loudness.
    """
    order = list(config.events)
    wanted = [e for e in events if e[0] in config.events and config.events[e[0]].sounds and e[1] < total_s]
    tracks: list[dict] = []
    counts: Counter = Counter()
    missing: set[str] = set()
    last = float("-inf")
    for kind, t, idx in sorted(wanted, key=lambda e: (e[1], order.index(e[0]))):
        if t - last < config.min_gap_s:
            continue
        ev = config.events[kind]
        n = counts[kind]
        name = ev.sounds[min(idx, len(ev.sounds) - 1)] if kind == "beat" else ev.sounds[n % len(ev.sounds)]
        path = library.get(name)
        if path is None:
            missing.add(name)
            continue
        peak_s, peak_db, dur = analyze(str(path))
        start = t - peak_s
        source_start = max(0.0, -start)
        start = max(0.0, start)
        tracks.append({
            "path": str(path),
            "source_start": source_start,
            "start": start,
            "end": min(total_s, start + dur - source_start),
            "gain_db": ev.gain_db,
            "slow_pct": 0.0,
            "peak_db": peak_db,
            "level_db": config.level_db,
        })
        counts[kind] += 1
        last = t
    for name in sorted(missing):
        warnings.append(f"Unknown sound effect: '{name}' (no such file in assets/sfx/)")
    return tracks
