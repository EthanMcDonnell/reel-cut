"""Multi-hook split — slice a multi-hook take into N standalone variant docs.

A single teleprompter take records N alternative hooks up front followed by one
shared body. Each variant video = hook_i + the shared body, rendered as a complete
standalone video so every "once per video" feature (logo first-occurrence, heading,
concept gag) is correct for free. This module holds the pure, deterministic slicing
logic; the LLM-authored boundaries live in `hooks.json` and the `reelcut split-hooks`
command drives it.

All times here are **source-clip seconds** (same timeline as captions words/edl),
except `make_variant_heading`, which emits **output-timeline** seconds for the card.
"""
from __future__ import annotations

import math
from dataclasses import replace

from .captions_doc import CaptionsDoc, EdlEntry
from .heading import _SERIES_TOKEN_RE


def edl_edges(edl: list[EdlEntry]) -> list[float]:
    """Sorted set of every EDL entry start/end — the legal boundary positions."""
    edges: set[float] = set()
    for e in edl:
        edges.add(round(e.start, 4))
        edges.add(round(e.end, 4))
    return sorted(edges)


def snap_boundary(t: float, edges: list[float], tolerance: float = 0.3) -> float:
    """Snap a boundary time to the nearest EDL edge so a slightly-off boundary never
    cuts mid-segment. Fail loudly if the nearest edge is further than `tolerance`."""
    if not edges:
        raise ValueError("no EDL edges to snap to")
    nearest = min(edges, key=lambda e: abs(e - t))
    if abs(nearest - t) > tolerance:
        raise ValueError(
            f"boundary {t:.3f}s is {abs(nearest - t):.3f}s from the nearest EDL edge "
            f"({nearest:.3f}s) — exceeds tolerance {tolerance}s; would cut mid-segment"
        )
    return nearest


def _clip_edl(edl: list[EdlEntry], r_start: float, r_end: float) -> list[EdlEntry]:
    """Return EDL entries intersected with [r_start, r_end), preserving keep/reason."""
    out: list[EdlEntry] = []
    for e in edl:
        s = max(e.start, r_start)
        en = min(e.end, r_end)
        if en - s > 1e-6:
            out.append(replace(e, start=round(s, 4), end=round(en, 4)))
    return out


def build_variant_doc(
    master: CaptionsDoc, hook_range: tuple[float, float], body_start: float
) -> CaptionsDoc:
    """Return a CaptionsDoc containing only `hook_range ∪ [body_start, ∞)`.

    The span between the hook and the body (the other hooks + their pauses) is
    replaced by a single cut entry so the EDL stays a continuous partition — the
    output-timeline remap then places body words right after the hook with no gap.
    Boundaries are assumed pre-snapped to EDL edges (see `snap_boundary`)."""
    hook_start, hook_end = hook_range
    clip = (
        master.source_clips[0]
        if master.source_clips
        else (master.edl[0].source_clip if master.edl else "")
    )

    hook_edl = _clip_edl(master.edl, hook_start, hook_end)
    body_edl = _clip_edl(master.edl, body_start, math.inf)

    new_edl = list(hook_edl)
    if body_start - hook_end > 1e-6:
        new_edl.append(
            EdlEntry(
                source_clip=clip,
                start=round(hook_end, 4),
                end=round(body_start, 4),
                keep=False,
                reason="outtake",
            )
        )
    new_edl.extend(body_edl)

    new_words = [
        w for w in master.words
        if hook_start <= w.start < hook_end or w.start >= body_start
    ]
    return CaptionsDoc(source_clips=list(master.source_clips), edl=new_edl, words=new_words)


def hook_output_duration(edl: list[EdlEntry], hook_range: tuple[float, float]) -> float:
    """Length of the hook on the variant's output timeline = sum of kept EDL
    durations intersected with `hook_range`. Used for the heading's end time."""
    hook_start, hook_end = hook_range
    total = 0.0
    for e in edl:
        if not e.keep:
            continue
        s = max(e.start, hook_start)
        en = min(e.end, hook_end)
        if en > s:
            total += en - s
    return round(total, 4)


def filter_images(images: list[dict], included_ranges: list[tuple[float, float]]) -> list[dict]:
    """Keep image specs whose (source-clip) start falls inside the variant's ranges.

    Body-anchored images survive in every variant; a hook-region image only goes to
    its own variant. Operates on raw dicts to round-trip images.json untouched."""
    def included(t: float) -> bool:
        return any(lo <= t <= hi for lo, hi in included_ranges)

    return [img for img in images if included(float(img.get("start", 0.0)))]


def make_variant_heading(
    hook: dict, hook_output_duration_s: float, episode_number: int | None
) -> dict:
    """Build the variant's single heading card (output-timeline seconds).

    `start=0`, `end=hook_output_duration_s` (the heading covers exactly the hook).
    Any `{n:<series>}` token in the title/subtitle is baked to the literal
    `episode_number` so the variant never touches the series registry (§8)."""
    heading = {
        "title": _bake_episode(hook.get("title", ""), episode_number),
        "subtitle": _bake_episode(hook.get("subtitle", ""), episode_number),
        "start": 0.0,
        "end": round(hook_output_duration_s, 4),
    }
    if "scrim" in hook:
        heading["scrim"] = hook["scrim"]
    return heading


def _bake_episode(text: str, episode_number: int | None) -> str:
    if not text or "{n:" not in text:
        return text
    if episode_number is None:
        raise ValueError("hook heading has a {n:<series>} token but no episode number was resolved")
    return _SERIES_TOKEN_RE.sub(str(episode_number), text)
