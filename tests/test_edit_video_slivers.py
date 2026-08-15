"""A cut must not leave a keep span too short to render, or fragment the EDL.

When a --cut boundary lands a few milliseconds inside an existing keep span, the
remnant stays in the EDL as its own keep entry. h264_videotoolbox cannot open an
encoder for a segment that short, so render-hooks dies on "Could not open encoder
before EOF" — an error that never names the offending span. Absorbing the remnant
into the cut is what keeps the render alive.

Eligibility is adjacency to a cut this tool made, not position on the timeline:
short keeps that predate the edit render fine (120ms and 150ms spans ship in real
videos) and flipping one would shift the output timeline under the title cards.
"""
from scrape.edit_video import (
    CUT_REASON,
    SLIVER_REASON,
    _absorb_remnants,
    _apply_cut,
    _merge_adjacent_cuts,
    _min_keep_s,
)
from reelcut.captions_doc import EdlEntry

CLIP = "assets/demo/clip.MOV"
FLOOR = 0.1


def _keeps(edl):
    return [(round(e.start, 3), round(e.end, 3)) for e in edl if e.keep]


def test_cut_landing_inside_a_keep_span_leaves_an_unrenderable_sliver():
    """The bug itself: without absorption, _apply_cut strands a 10ms keep entry."""
    edl = [EdlEntry(CLIP, 74.990, 80.0, True, "speech")]

    out = _apply_cut(edl, 75.0, 80.0)

    assert (74.990, 75.0) in _keeps(out)
    assert any(e.keep and e.end - e.start < FLOOR for e in out)


def test_remnant_of_our_own_cut_is_absorbed():
    edl = _apply_cut([EdlEntry(CLIP, 74.990, 80.0, True, "speech")], 75.0, 80.0)

    out, absorbed = _absorb_remnants(edl, FLOOR)

    assert _keeps(out) == []
    assert [a["duration"] for a in absorbed] == [0.01]
    assert all(e.reason in (SLIVER_REASON, CUT_REASON) for e in out if not e.keep)


def test_spans_long_enough_to_render_are_left_alone():
    """0.69s held the closing line of a real video — absorption must not eat it."""
    edl = _apply_cut(
        [EdlEntry(CLIP, 10.0, 20.0, True, "speech"),
         EdlEntry(CLIP, 84.290, 84.980, True, "speech")],
        20.0, 84.290,
    )

    out, absorbed = _absorb_remnants(edl, FLOOR)

    assert _keeps(out) == [(10.0, 20.0), (84.29, 84.98)]
    assert absorbed == []


def test_short_keep_not_adjacent_to_our_cut_is_untouched():
    """It predates the edit and renders fine; flipping it would shift the timeline."""
    edl = [
        EdlEntry(CLIP, 1.0, 1.005, True, "speech"),      # pre-existing sliver
        EdlEntry(CLIP, 1.005, 74.990, False, "silence"),  # not one of ours
        EdlEntry(CLIP, 74.990, 80.0, True, "speech"),
    ]
    edl = _apply_cut(edl, 75.0, 80.0)

    out, absorbed = _absorb_remnants(edl, FLOOR)

    assert (1.0, 1.005) in _keeps(out)
    assert [a["start"] for a in absorbed] == [74.990]


def test_remnant_just_before_the_tail_guard_is_still_absorbed():
    """The case a position-based sweep missed — and the one that kills renders."""
    edl = _apply_cut([EdlEntry(CLIP, 7.50, 20.0, True, "speech")], 7.55, 15.0)

    out, absorbed = _absorb_remnants(edl, FLOOR)

    assert [a["start"] for a in absorbed] == [7.50]
    assert (7.50, 7.55) not in _keeps(out)


def test_repeated_cuts_do_not_fragment_the_edl():
    """Three cuts on one clip produced 28 spans over 14 contiguous runs before this."""
    edl = [EdlEntry(CLIP, 0.0, 100.0, True, "speech")]
    for lo, hi in ((10.0, 20.0), (20.0, 30.0), (30.0, 40.0)):
        edl = _apply_cut(edl, lo, hi)

    merged = _merge_adjacent_cuts(edl)

    assert [(e.start, e.end, e.keep) for e in merged] == [
        (0.0, 10.0, True),
        (10.0, 40.0, False),
        (40.0, 100.0, True),
    ]


def test_keep_floor_comes_from_the_pipeline_config():
    """Not a second constant: the same cuts.min_keep_ms _optimize_edl builds EDLs with."""
    from reelcut.config import load_config
    from scrape.edit_video import CONFIG_PATH

    assert _min_keep_s() == load_config(CONFIG_PATH).cuts.min_keep_ms / 1000.0
