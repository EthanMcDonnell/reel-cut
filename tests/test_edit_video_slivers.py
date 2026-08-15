"""A cut must not leave a keep span too short to render.

When a --cut boundary lands a few milliseconds inside an existing keep span, the
remnant stays in the EDL as its own keep entry. h264_videotoolbox cannot open an
encoder for a segment that short, so render-hooks dies on "Could not open encoder
before EOF" — an error that never names the offending span. Absorbing the remnant
into the cut is what keeps the render alive.
"""
from scrape.edit_video import MIN_KEEP_S, SLIVER_REASON, _absorb_slivers, _apply_cut
from reelcut.captions_doc import EdlEntry

CLIP = "assets/demo/clip.MOV"


def _keeps(edl):
    return [(round(e.start, 3), round(e.end, 3)) for e in edl if e.keep]


def test_cut_landing_inside_a_keep_span_leaves_an_unrenderable_sliver():
    """The bug itself: without absorption, _apply_cut strands a 10ms keep entry."""
    edl = [EdlEntry(CLIP, 74.990, 80.0, True, "speech")]

    out = _apply_cut(edl, 75.0, 80.0)

    assert (74.990, 75.0) in _keeps(out)
    assert any(e.keep and e.end - e.start < MIN_KEEP_S for e in out)


def test_sliver_in_the_tail_is_absorbed_into_the_cut():
    edl = _apply_cut([EdlEntry(CLIP, 74.990, 80.0, True, "speech")], 75.0, 80.0)

    out, absorbed = _absorb_slivers(edl, tail_start=7.5)

    assert _keeps(out) == []
    assert [a["duration"] for a in absorbed] == [0.01]
    assert all(e.reason == SLIVER_REASON for e in out if not e.keep and e.end <= 75.0)


def test_spans_long_enough_to_render_are_left_alone():
    """0.69s held the closing line of a real video — absorption must not eat it."""
    edl = [
        EdlEntry(CLIP, 10.0, 20.0, True, "speech"),
        EdlEntry(CLIP, 84.290, 84.980, True, "speech"),
    ]

    out, absorbed = _absorb_slivers(edl, tail_start=7.5)

    assert _keeps(out) == [(10.0, 20.0), (84.29, 84.98)]
    assert absorbed == []


def test_slivers_before_the_tail_guard_are_not_touched():
    """Removing one would shift the output timeline under the burned-in title cards."""
    edl = [
        EdlEntry(CLIP, 1.0, 1.005, True, "speech"),
        EdlEntry(CLIP, 74.990, 75.0, True, "speech"),
    ]

    out, absorbed = _absorb_slivers(edl, tail_start=7.5)

    assert _keeps(out) == [(1.0, 1.005)]
    assert [a["start"] for a in absorbed] == [74.990]
