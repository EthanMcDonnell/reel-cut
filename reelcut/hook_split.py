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


def snap_windows(edl, words, hook_windows: list[tuple[float, float]], max_lead: float = 1.0):
    """Move each hook-window edge back to the EDL seam just before it.

    /produce-video sets a window edge at the next section's first *word*, but its keep
    entry starts earlier — the transcriber pads every keep with pre-roll before the first
    word. Partitioning at the word puts that pre-roll in the previous section: each hook
    video ends with a flash of the next hook's take, and the body loses its lead-in in
    every video but the last hook's. Snapping to the seam (an output time where a keep
    entry starts) gives the pre-roll to the section it belongs to.

    An edge only moves if a seam lies within `max_lead` before it with no word starting
    in between, so hooks spoken back to back with no cut keep their word-level split.
    """
    from .cli import _build_edl_remap

    remap, _ = _build_edl_remap(edl)
    seams = sorted(remap(e.source_clip, e.start) for e in edl if e.keep)
    word_starts = sorted(remap(w.source_clip, w.start) for w in words)
    EPS = 1e-3

    def snap(t: float) -> float:
        candidates = [s for s in seams if t - max_lead <= s <= t + EPS]
        if not candidates:
            return t
        s = candidates[-1]
        if any(s + EPS < w < t - EPS for w in word_starts):
            return t
        return min(s, t)

    return [(snap(s), snap(e)) for s, e in hook_windows]


def build_hook_edl(edl, hook_windows: list[tuple[float, float]], target_idx: int):
    """Build the EDL for the video that keeps only hook `target_idx` + body.

    Args:
        edl: list of doc EdlEntry (has .source_clip/.start/.end/.keep/.reason).
        hook_windows: [(start, end), …] output-timeline, one per titled hook card.
        target_idx: which hook to keep.

    Returns:
        (new_edl, hook_dur, drop_intervals)
        - new_edl: copies of every entry; keep entries are split at hook-window
          boundaries (hooks aren't separated by EDL cuts, so one keep entry can
          straddle several hooks), and any resulting piece outside hook
          `target_idx` + body is flipped to keep=False (reason="outtake").
        - hook_dur: output duration of the kept hook — its rebased title-card end.
        - drop_intervals: {source_clip: [(start, end), …]} source-time ranges of the
          dropped pieces, for removing their words/images.
    """
    from .cli import _build_edl_remap

    remap, _ = _build_edl_remap(edl)
    body_start = hook_windows[-1][1]
    # Output-time boundaries between sections (hook starts + body start).
    boundaries = sorted({s for s, _ in hook_windows} | {body_start})

    new_edl = []
    hook_dur = 0.0
    drop_intervals: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for e in edl:
        if not e.keep:
            new_edl.append(dataclasses.replace(e))
            continue
        # Within a keep entry, output time advances linearly with source time
        # (no interior cuts), so a boundary at output `b` maps to source
        # `e.start + (b - o_start)`. Split at every boundary interior to the entry.
        # The EPS margin keeps a boundary that lands *on* an entry edge from counting
        # as interior: `o_end` is accumulated through the remap, so a boundary equal to
        # it can compare a few float-ulps below (e.g. 22.115 < 22.115000000000006) and
        # split off a zero-length piece, which extracts to a corrupt segment and
        # silently truncates the concat. Real EDL cuts are never 1ms apart.
        EPS = 1e-3
        o_start = remap(e.source_clip, e.start)
        o_end = o_start + (e.end - e.start)
        edges = [o_start] + [b for b in boundaries if o_start + EPS < b < o_end - EPS] + [o_end]
        for lo, hi in zip(edges, edges[1:]):
            s_lo = e.start + (lo - o_start)
            s_hi = e.start + (hi - o_start)
            section = _section_of(lo, hook_windows, body_start)
            if section == "body" or section == target_idx:
                new_edl.append(dataclasses.replace(e, start=s_lo, end=s_hi))
                if section == target_idx:
                    hook_dur += hi - lo
            else:
                new_edl.append(dataclasses.replace(e, start=s_lo, end=s_hi, keep=False, reason="outtake"))
                drop_intervals[e.source_clip].append((s_lo, s_hi))

    return new_edl, round(hook_dur, 4), dict(drop_intervals)


def drop_covered(items, drop_intervals: dict[str, list[tuple[float, float]]]):
    """Keep only items whose `start` is NOT inside any dropped interval on their
    source clip. Works for CaptionWord and ImageSpec (both have .source_clip and
    .start).

    A dropped interval ends at a section boundary, and the next section's first
    word starts exactly there — but the interval's upper bound is derived through
    the output-time remap, which can round it a hair *above* the word start (float
    imprecision). Without tolerance that first word is wrongly swept into the
    previous section and dropped (its caption vanishes from the render). The 1ms
    EPS on the upper edge excludes it; no real word starts within 1ms of a section
    boundary, since sections are separated by EDL cuts.

    A dropped section can span several intervals (EDL splits leave interior seams
    at kept-hook boundaries). Coalesce touching intervals first so the EPS applies
    only to a run's true outer edge — otherwise a word sitting on an interior seam
    would leak through the 1ms hole and be wrongly kept."""
    EPS = 1e-3
    merged: dict[str, list[tuple[float, float]]] = {}
    for clip, ivs in drop_intervals.items():
        run: list[tuple[float, float]] = []
        for s, e in sorted(ivs):
            if run and s <= run[-1][1] + EPS:
                run[-1] = (run[-1][0], max(run[-1][1], e))
            else:
                run.append((s, e))
        merged[clip] = run
    out = []
    for it in items:
        intervals = merged.get(it.source_clip, [])
        if any(s <= it.start < e - EPS for s, e in intervals):
            continue
        out.append(it)
    return out
