"""Captions must not survive a cut their audio didn't.

captions.json carries no per-word keep flag, so every word reloaded in Phase 2
defaults to keep=True. Filtering captions on that flag alone silently captions a
cut retake over the top of the take that replaced it.
"""
from reelcut.cli import _remap_kept_words
from reelcut.edl import EDLEntry
from reelcut.transcriber import WordTimestamp

CLIP = "assets/demo/clip.MOV"


def test_words_inside_a_cut_span_are_not_captioned_even_when_flagged_keep():
    edl = [
        EDLEntry(start=0.0, end=2.0, keep=True, source_clip=CLIP, reason="speech"),
        EDLEntry(start=2.0, end=4.0, keep=False, source_clip=CLIP, reason="retake"),
        EDLEntry(start=4.0, end=6.0, keep=True, source_clip=CLIP, reason="speech"),
    ]
    # keep defaults to True on every word — exactly what load_captions_doc produces.
    words = [
        WordTimestamp(word=w, start=s, end=s + 0.3, confidence=1.0, clip_path=CLIP)
        for w, s in [("kept", 0.5), ("ghost", 2.5), ("also-ghost", 3.5), ("kept-too", 4.5)]
    ]

    out = _remap_kept_words(words, edl)

    assert [w.word for w in out] == ["kept", "kept-too"]


def test_word_on_a_hook_boundary_is_not_swallowed_by_float_drift():
    """Regression (utf-8-character-encoding, "See," at 50.9s): the first word of the
    body lost its caption in 8 of 10 hook renders.

    render-hooks splits a keep entry at the hook/body boundary and flips the piece
    outside the target hook to a cut. That piece's end comes back through the
    output-time remap as 50.900000000000006 while the word starts at exactly 50.9, so
    `s <= w.start < e` counted the word as cut. The audio still said it and
    captions.json still held it, so nothing downstream could notice.

    Only the hook that owned the preceding piece (no cut span there at all) kept the
    caption — which is exactly how it showed up as "missing from most of the videos".
    """
    boundary = 50.9
    # build_hook_edl derives the split point through the output-time remap, so the
    # outtake piece ENDS a float-ulp above the boundary the word starts on.
    drifted = 50.900000000000006
    assert drifted > boundary, "the drift this guards against must be representable"
    edl = [
        EDLEntry(start=40.0, end=drifted, keep=False, source_clip=CLIP, reason="outtake"),
        EDLEntry(start=drifted, end=60.0, keep=True, source_clip=CLIP, reason="speech"),
    ]
    words = [
        WordTimestamp(word=w, start=s, end=s + 0.16, confidence=1.0, clip_path=CLIP)
        for w, s in [("See,", boundary), ("a", 51.18), ("text", 51.32)]
    ]

    out = _remap_kept_words(words, edl)

    assert [w.word for w in out] == ["See,", "a", "text"]


def test_word_on_a_seam_between_two_touching_cuts_is_still_dropped(): 
    """The boundary tolerance must not open a 1ms hole mid-cut.

    Adjacent EDL cut entries touch (silence then breath), so a word starting exactly on
    that interior seam sits 1ms inside the second span. Coalescing the run first keeps
    the tolerance on its true outer edge only.
    """
    edl = [
        EDLEntry(start=0.0, end=2.0, keep=True, source_clip=CLIP, reason="speech"),
        EDLEntry(start=2.0, end=4.0, keep=False, source_clip=CLIP, reason="silence"),
        EDLEntry(start=4.0, end=6.0, keep=False, source_clip=CLIP, reason="breath"),
        EDLEntry(start=6.0, end=8.0, keep=True, source_clip=CLIP, reason="speech"),
    ]
    words = [
        WordTimestamp(word=w, start=s, end=s + 0.3, confidence=1.0, clip_path=CLIP)
        for w, s in [("kept", 0.5), ("on-the-seam", 4.0), ("kept-too", 6.0)]
    ]

    out = _remap_kept_words(words, edl)

    assert [w.word for w in out] == ["kept", "kept-too"]
