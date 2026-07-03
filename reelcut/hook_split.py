"""Split a full-take EDL into per-hook variants.

`reelcut render` renders the whole take (hook1 → hook2 → … → body) as one video.
`reelcut render-hooks` instead produces one video per hook, each pairing that hook
with the shared body. This module computes, for a target hook, the filtered EDL
(the other hooks flipped to cuts) plus the source-time intervals of the dropped
hooks so their words/images can be removed. No I/O — pure functions.
"""
from __future__ import annotations

import dataclasses
from collections import defaultdict


def _section_of(o: float, hook_windows: list[tuple[float, float]], body_start: float):
    """Which section an output-timeline position `o` belongs to: a hook index
    (0-based int) or "body".

    Partition boundaries are the hook card *starts* (plus body_start as the final
    sentinel), so minor start/end fuzz can't misfile an entry. Anything before the
    first hook start folds into hook 0.
    """
    if o >= body_start:
        return "body"
    for k in range(len(hook_windows)):
        upper = hook_windows[k + 1][0] if k + 1 < len(hook_windows) else body_start
        if o < upper:
            return k
    return len(hook_windows) - 1  # o < body_start guarantees a hit above; safety net


def build_hook_edl(edl, hook_windows: list[tuple[float, float]], target_idx: int):
    """Build the EDL for the video that keeps only hook `target_idx` + body.

    Args:
        edl: list of doc EdlEntry (has .source_clip/.start/.end/.keep/.reason).
        hook_windows: [(start, end), …] output-timeline, one per titled hook card.
        target_idx: which hook to keep.

    Returns:
        (new_edl, hook_dur, drop_intervals)
        - new_edl: copies of every entry; keep entries belonging to the *other*
          hooks are flipped to keep=False (reason="outtake").
        - hook_dur: output duration of the kept hook — its rebased title-card end.
        - drop_intervals: {source_clip: [(start, end), …]} source-time ranges of the
          dropped hooks, for removing their words/images.
    """
    from .cli import _build_edl_remap

    remap, _ = _build_edl_remap(edl)
    body_start = hook_windows[-1][1]

    new_edl = []
    hook_dur = 0.0
    drop_intervals: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for e in edl:
        if not e.keep:
            new_edl.append(dataclasses.replace(e))
            continue
        section = _section_of(remap(e.source_clip, e.start), hook_windows, body_start)
        if section == "body" or section == target_idx:
            new_edl.append(dataclasses.replace(e))
            if section == target_idx:
                hook_dur += e.end - e.start
        else:
            new_edl.append(dataclasses.replace(e, keep=False, reason="outtake"))
            drop_intervals[e.source_clip].append((e.start, e.end))

    return new_edl, round(hook_dur, 4), dict(drop_intervals)


def drop_covered(items, drop_intervals: dict[str, list[tuple[float, float]]]):
    """Keep only items whose `start` is NOT inside any dropped interval on their
    source clip. Works for CaptionWord and ImageSpec (both have .source_clip and
    .start)."""
    out = []
    for it in items:
        intervals = drop_intervals.get(it.source_clip, [])
        if any(s <= it.start < e for s, e in intervals):
            continue
        out.append(it)
    return out
