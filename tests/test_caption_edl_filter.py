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
