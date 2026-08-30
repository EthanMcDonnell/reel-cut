"""Every word a hook variant speaks must be captioned in that variant.

The per-hook filters (drop_covered on source intervals, _remap_kept_words on cut spans)
both round at a section boundary, and a word that falls between them loses its caption
in the render while staying in captions.json and in the audio. Nothing downstream can
see that — this check is the only mechanical signal.
"""
from reelcut.captions_doc import CaptionsDoc, CaptionWord, EdlEntry
from reelcut.cli import _hook_caption_survival

CLIP = "c.mp4"

# Two adjacent keep entries, no cuts, so output time == source time. The hook/body
# boundary at 50.9 is the one that bites: build_hook_edl derives the split point as
# 2.09 + (50.9 - 2.09), which is 50.900000000000006 — a float-ulp above the boundary
# the body's first word starts on.
EDL = [
    EdlEntry(source_clip=CLIP, start=0.0, end=2.09, keep=True, reason="speech"),
    EdlEntry(source_clip=CLIP, start=2.09, end=70.0, keep=True, reason="speech"),
]
HOOK_WINDOWS = [(0.0, 2.09), (2.09, 26.5), (26.5, 50.9)]
WORDS = [
    CaptionWord(word=w, start=s, end=s + 0.16, source_clip=CLIP)
    for w, s in [
        ("hook1-a", 0.5), ("hook1-b", 1.2),
        ("hook2-a", 3.0), ("hook2-b", 20.0),
        ("hook3-a", 27.0), ("hook3-b", 40.0),
        ("See,", 50.9), ("a", 51.18), ("text", 51.32),
    ]
]


def _doc(words=None, edl=None):
    return CaptionsDoc(source_clips=[CLIP], edl=edl or EDL, words=words or WORDS)


def _pre_fix_in_cut_run(clip, start, runs):
    """`_in_cut_run` as it was before the boundary fix — no tolerance on the upper edge."""
    return any(s <= start < e for s, e in runs.get(clip, []))


def test_every_word_survives_into_the_variants_that_speak_it():
    assert _hook_caption_survival(_doc(), HOOK_WINDOWS) == []


def test_reports_the_body_word_the_boundary_drift_swallows(monkeypatch):
    """Fault injection: with the pre-fix filter restored, the check must name the word.

    This is the utf-8-character-encoding failure exactly — "See," at 50.9s lost from
    every variant whose hook precedes the boundary, kept only by the one that owns the
    piece before it (hook 3, which has no cut span there at all).
    """
    monkeypatch.setattr("reelcut.cli._in_cut_run", _pre_fix_in_cut_run)

    warnings = _hook_caption_survival(_doc(), HOOK_WINDOWS)

    assert len(warnings) == 2
    assert warnings[0].startswith("Hook 1: 1 word(s)")
    assert warnings[1].startswith("Hook 2: 1 word(s)")
    assert all("'See,' @ 50.90s" in w for w in warnings)


def test_a_word_cut_from_the_full_take_is_owed_no_caption():
    """A dropped retake is captioned by no variant, and that is not a loss."""
    edl = [
        EdlEntry(source_clip=CLIP, start=0.0, end=2.09, keep=True, reason="speech"),
        EdlEntry(source_clip=CLIP, start=2.09, end=30.0, keep=True, reason="speech"),
        EdlEntry(source_clip=CLIP, start=30.0, end=34.0, keep=False, reason="retake"),
        EdlEntry(source_clip=CLIP, start=34.0, end=70.0, keep=True, reason="speech"),
    ]
    words = WORDS + [CaptionWord(word="fluffed", start=31.0, end=31.4, source_clip=CLIP)]

    assert _hook_caption_survival(_doc(words=words, edl=edl), HOOK_WINDOWS) == []


def test_a_word_lost_to_a_hole_in_drop_covered_is_reported(monkeypatch):
    """The other filter counts too: if drop_covered starts dropping body words, say so."""
    monkeypatch.setattr(
        "reelcut.hook_split.drop_covered",
        lambda items, intervals: [w for w in items if w.word != "text"],
    )

    warnings = _hook_caption_survival(_doc(), HOOK_WINDOWS)

    assert len(warnings) == len(HOOK_WINDOWS)
    assert all("'text' @ 51.32s" in w for w in warnings)
