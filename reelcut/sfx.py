"""Sound effects — automatic ones on the render's own events, plus sounds placed in sfx.json.

Automatic events come from the render's cues (overlay starts, animated-card beats, heading
cards); `sfx.events` in config.yaml picks which fire. Placed sounds are listed per video in
`assets/<slug>/sfx.json`. Each effect is shifted so its loudest moment lands on its frame — a
whoosh builds before its peak, a click peaks at once — and an effect closer than
`sfx.min_gap_s` to the one before is dropped, so a burst of events gets one sound.
"""
from __future__ import annotations

from collections import Counter
from functools import lru_cache
from pathlib import Path

from .config import SfxConfig

_SR = 48000
_AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus"}


def sfx_events(cues: list, headings: list[tuple[str, float]]) -> list[tuple[str, float, int]]:
    """(event, output-timeline second, index) for every overlay start, card beat and title card.

    An animated card renders as a `video` cue with kind "card", so it fires `card`, not `video`.
    A beat's index is its position in the card; beats past the cue's end (cut off at a hook
    boundary) are skipped. `headings` are each title card's (event, second) — the moment it
    lands, as `heading` or `heading_<entrance>` — which the caller works out.
    """
    events = []
    for c in cues:
        events.append(("card" if c.kind == "card" else c.type, c.start, 0))
        events.extend(("beat", b, i) for i, b in enumerate(c.beats) if b < c.end)
    events.extend((kind, t, 0) for kind, t in headings)
    return events


def sfx_library(sfx_dir: Path) -> dict[str, Path]:
    """Sound files anywhere under `sfx_dir`, keyed by file stem."""
    if not sfx_dir.is_dir():
        return {}
    return {p.stem: p for p in sorted(sfx_dir.rglob("*")) if p.suffix.lower() in _AUDIO_EXTS}


def load_sfx_cues(path: Path) -> list[dict]:
    """sfx.json — a JSON list of placed sounds: {"sound": <stem>, "at": <source-clip seconds>,
    "source_clip": <path>, "gain_db": <trim>}. Missing file → []."""
    if not path.exists():
        return []
    import json
    return json.loads(path.read_text())


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
    placed: list[tuple[str, float, float]] = (),
    cuts: list[float] = (),
    tol_s: float = 0.05,
) -> list[dict]:
    """Renderer-ready track dicts for `events` and `placed` (sound, output second, gain_db),
    peak-aligned and rate-limited. A placed sound wins a tie with an automatic one.

    A sound marks something changing on screen, so a placed one must land on an event (an
    overlay, card beat or title card) or a cut (`cuts`, output seconds); one on a bare word
    is dropped with a warning.

    Each dict carries `peak_db` and `level_db`, which the renderer's leveling uses to set the
    effect's peak relative to the voice instead of measuring its integrated loudness.
    """
    order = list(config.events)
    wanted = [e for e in events if e[0] in config.events and config.events[e[0]].sounds and e[1] < total_s]
    tracks: list[dict] = []
    counts: Counter = Counter()
    missing: set[str] = set()
    last = float("-inf")
    items = [(t, order.index(kind), kind, idx, "", 0.0) for kind, t, idx in wanted]
    moments = [t for _, t, _ in events] + list(cuts)
    for name, t, gain in placed:
        if not any(abs(t - m) <= tol_s for m in moments):
            warnings.append(f"Sound '{name}' at {t:.2f}s is on no overlay, title or cut — dropped")
    placed = [p for p in placed if any(abs(p[1] - m) <= tol_s for m in moments)]
    items += [(t, -1, "placed", 0, name, gain) for name, t, gain in placed if t < total_s]
    for t, _, kind, idx, name, gain_db in sorted(items, key=lambda e: e[:2]):
        if t - last < config.min_gap_s:
            continue
        if kind != "placed":
            ev = config.events[kind]
            n = counts[kind]
            name = ev.sounds[min(idx, len(ev.sounds) - 1)] if kind == "beat" else ev.sounds[n % len(ev.sounds)]
            gain_db = ev.gain_db
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
            "gain_db": gain_db,
            "slow_pct": 0.0,
            "peak_db": peak_db,
            "level_db": config.level_db,
        })
        counts[kind] += 1
        last = t
    for name in sorted(missing):
        warnings.append(f"Unknown sound effect: '{name}' (no such file in assets/sfx/)")
    return tracks
