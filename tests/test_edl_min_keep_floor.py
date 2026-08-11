"""Regression tests for the min_keep_ms floor in generate_scriptless_edl.

The floor exists to give a sub-token word ("-2026" in "CVE-2026-31431") a minimum
audible window before the cut. It used to be applied as an assignment, which meant it
could also move the cut boundary *backwards* — undoing the trailing-speech scan and
clipping the word it was supposed to protect. These two tests pin both directions.
"""
from reelcut.edl import generate_scriptless_edl
from reelcut.gap_detector import Gap
from reelcut.transcriber import WordTimestamp

CLIP = "clip.mov"


def _words(*specs: tuple[str, float, float, float]) -> list[WordTimestamp]:
    return [
        WordTimestamp(word=w, start=s, end=e, confidence=c, clip_path=CLIP)
        for w, s, e, c in specs
    ]


def _gap(start: float, end: float, speech_end: float) -> Gap:
    return Gap(
        start=start, end=end, effective_start=start, speech_end=speech_end,
        duration_ms=(end - start) * 1000, gap_type="noise", cut=True,
    )


def test_floor_does_not_pull_the_cut_back_inside_a_tail_truncated_word():
    """casual-talking-head, 16.4s: "1 million for API?" clipped to "1 million for A-p".

    wav2vec2 aligned 'API?' to 122 ms (16.405→16.527) while the spoken word ran to
    17.147s. gap.speech_end had already found the real end, but 122 ms < min_keep_ms
    (200) so the floor overwrote the cut with 16.405 + 0.200 = 16.605 — 542 ms inside
    the word. The cut must open at the speech end, not at the floor.
    """
    words = _words(
        ("for", 16.202, 16.365, 0.62),
        ("API?", 16.405, 16.527, 0.47),
        ("I", 18.430, 18.510, 0.95),
    )
    gaps = [_gap(16.527, 18.430, speech_end=17.147)]

    edl = generate_scriptless_edl(words, gaps, min_keep_ms=200, speech_pad_ms=150)

    cut = next(e for e in edl if not e.keep)
    assert cut.start == 17.147


def test_floor_still_extends_a_cut_that_would_clip_a_sub_token_word():
    """The case the floor was built for must keep working.

    'CVE-2026-31431' splits into sub-tokens WhisperX can assign < 50 ms to. Here the
    audio genuinely goes silent at the aligned end (speech_end == word end), so cutting
    there would leave the token inaudible. The floor pushes the cut out to 200 ms.
    """
    words = _words(
        ("CVE-", 10.000, 10.300, 0.90),
        ("2026", 10.300, 10.340, 0.90),
        ("next", 14.000, 14.300, 0.90),
    )
    gaps = [_gap(10.340, 14.000, speech_end=10.340)]

    edl = generate_scriptless_edl(words, gaps, min_keep_ms=200, speech_pad_ms=150)

    cut = next(e for e in edl if not e.keep)
    assert cut.start == 10.500
