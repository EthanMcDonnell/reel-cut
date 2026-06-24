"""Multi-hook split — slice a multi-hook take into per-segment docs for concat.

A single teleprompter take records N alternative hooks up front followed by one
shared body. We slice each hook and the body into their own independent segment doc,
render each **once**, then `ffmpeg`-concatenate `hookN + body` into N final videos —
so the body is encoded once, not N times. (Tradeoff: logos are deduped per render, so
a brand named in both a hook and the body shows its logo in each.) This module holds
the pure, deterministic slicing logic; the LLM-authored boundaries live in `hooks.json`
and the `reelcut split-hooks` command drives it.

All times here are **source-clip seconds** (same timeline as captions words/edl),
except `make_variant_heading`, which emits **output-timeline** seconds for the card.
"""
from __future__ import annotations

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


def build_segment_doc(master: CaptionsDoc, start: float, end: float) -> CaptionsDoc:
    """Return a CaptionsDoc containing only the words+EDL in `[start, end)`.

    Each hook and the shared body are sliced into their own independent segment doc
    and rendered once; the finals are `ffmpeg`-concatenated (hookN + body) downstream.
    Boundaries are assumed pre-snapped to EDL edges (see `snap_boundary`). Use
    `end=math.inf` for the body (everything from body_start onward)."""
    new_edl = _clip_edl(master.edl, start, end)
    new_words = [w for w in master.words if start <= w.start < end]
    return CaptionsDoc(source_clips=list(master.source_clips), edl=new_edl, words=new_words)


def segment_output_duration(edl: list[EdlEntry], start: float, end: float) -> float:
    """Length of `[start, end)` on the output timeline = sum of kept EDL durations
    intersected with the range. Used for a hook's heading end time."""
    total = 0.0
    for e in edl:
        if not e.keep:
            continue
        s = max(e.start, start)
        en = min(e.end, end)
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
