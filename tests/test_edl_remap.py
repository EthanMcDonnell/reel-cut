"""Tests for _build_edl_remap — source-clip time → output-timeline time.

Image overlays are anchored in source time, so a later EDL change can move a cut over
one. A time inside a cut has no output frame of its own; the remap used to keep the
removed span's own duration and return a position matching nothing, which put an overlay
over whatever speech happened to follow.
"""
from reelcut.cli import _build_edl_remap
from reelcut.edl import EDLEntry

CLIP = "/x/clip.mp4"


def _edl():
    # keep 0–10, cut 10–20, keep 20–30  → output is 20s long
    return [
        EDLEntry(0.0, 10.0, True, CLIP, "speech"),
        EDLEntry(10.0, 20.0, False, CLIP, "silence"),
        EDLEntry(20.0, 30.0, True, CLIP, "speech"),
    ]


def test_kept_times_map_through_the_cut():
    remap, _ = _build_edl_remap(_edl())
    assert remap(CLIP, 0.0) == 0.0
    assert remap(CLIP, 10.0) == 10.0
    assert remap(CLIP, 20.0) == 10.0    # the splice
    assert remap(CLIP, 30.0) == 20.0


def test_time_inside_a_cut_snaps_to_the_splice():
    remap, _ = _build_edl_remap(_edl())
    # Every moment in 10–20 was removed, so all of them sit at the splice. Previously
    # 15.0 returned 15.0 — five seconds into footage that is not in the output.
    for t in (10.5, 15.0, 19.9):
        assert remap(CLIP, t) == 10.0


def test_remap_is_monotonic_across_a_cut():
    remap, _ = _build_edl_remap(_edl())
    times = [5.0, 9.9, 10.0, 12.0, 18.0, 20.0, 25.0]
    mapped = [remap(CLIP, t) for t in times]
    assert mapped == sorted(mapped)


def test_a_span_wholly_inside_a_cut_collapses_to_zero():
    # This is what lets the render drop such an overlay instead of drawing it somewhere
    # arbitrary for its full authored duration.
    remap, _ = _build_edl_remap(_edl())
    assert remap(CLIP, 16.2) - remap(CLIP, 15.28) == 0.0
