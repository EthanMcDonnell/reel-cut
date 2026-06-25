"""Tests for retake_detector.detect_retakes."""
import pytest
from reelcut.transcriber import WordTimestamp
from reelcut.retake_detector import detect_retakes


def _w(word: str, start: float, end: float) -> WordTimestamp:
    return WordTimestamp(word=word, start=start, end=end, confidence=0.9)


# ---------------------------------------------------------------------------
# Basic detection
# ---------------------------------------------------------------------------

def test_immediate_restart_exact_min_words():
    """Retake with no filler words between takes (j == i + min_retake_words).

    Previously missed due to j <= i + min_retake_words guard (off-by-one).
    'Things like cyber,' → 'things like cyber' with ~1s gap but no words between.
    """
    words = [
        _w("Things", 65.140, 65.321),
        _w("like",   65.361, 65.481),
        _w("cyber,", 65.562, 66.024),
        # second take starts immediately (j = i + 3 = i + min_retake_words)
        _w("things", 66.968, 67.148),
        _w("like",   67.168, 67.309),
        _w("cyber",  67.389, 67.731),
        _w("attacks,", 67.800, 68.200),
    ]
    ranges, candidates = detect_retakes(words, min_retake_words=3)
    assert len(ranges) == 1
    cut_start, cut_end = ranges[0]
    assert cut_start == pytest.approx(65.140)
    assert cut_end == pytest.approx(66.968)


def test_retake_with_filler_between():
    """Retake with filler words between takes (j > i + min_retake_words) still detected."""
    words = [
        _w("things", 1.0, 1.2),
        _w("like",   1.3, 1.5),
        _w("cyber",  1.6, 1.9),
        _w("uh",     2.0, 2.1),   # filler between takes
        _w("things", 2.2, 2.4),
        _w("like",   2.5, 2.7),
        _w("cyber",  2.8, 3.0),
        _w("attacks", 3.1, 3.5),
    ]
    ranges, candidates = detect_retakes(words, min_retake_words=3)
    assert len(ranges) == 1
    assert ranges[0][0] == pytest.approx(1.0)
    assert ranges[0][1] == pytest.approx(2.2)


def test_no_retake_for_unique_phrases():
    """Non-repeated phrases produce no cuts."""
    words = [
        _w("one",   0.0, 0.3),
        _w("two",   0.4, 0.7),
        _w("three", 0.8, 1.1),
        _w("four",  1.2, 1.5),
        _w("five",  1.6, 1.9),
    ]
    ranges, _ = detect_retakes(words, min_retake_words=3)
    assert ranges == []


def test_no_retake_below_min_words():
    """Phrase shorter than min_retake_words is not flagged."""
    words = [
        _w("hi",    0.0, 0.2),
        _w("there", 0.3, 0.5),
        _w("hi",    0.6, 0.8),
        _w("there", 0.9, 1.1),
        _w("world", 1.2, 1.5),
    ]
    ranges, _ = detect_retakes(words, min_retake_words=3)
    assert ranges == []


def test_gap_beyond_max_retake_gap_not_detected():
    """A repeated phrase beyond max_retake_gap_s is not a retake."""
    words = [
        _w("things", 0.0,  0.3),
        _w("like",   0.4,  0.7),
        _w("cyber",  0.8,  1.1),
        _w("things", 30.0, 30.3),
        _w("like",   30.4, 30.7),
        _w("cyber",  30.8, 31.1),
    ]
    ranges, _ = detect_retakes(words, min_retake_words=3, max_retake_gap_s=20.0)
    assert ranges == []


def test_ratio_below_threshold_skipped():
    """A repeated n-gram whose match doesn't extend far enough is not cut."""
    # "things like cyber" appears twice but diverges immediately after —
    # match_len == min_retake_words, cut_len >> min_retake_words → low ratio.
    words = [
        _w("things",  0.0, 0.3),
        _w("like",    0.4, 0.7),
        _w("cyber",   0.8, 1.1),
        _w("attacks", 1.2, 1.6),
        _w("are",     1.7, 1.9),
        _w("serious", 2.0, 2.4),
        _w("risks",   2.5, 2.9),
        _w("things",  3.0, 3.3),
        _w("like",    3.4, 3.7),
        _w("cyber",   3.8, 4.1),
        _w("defense", 4.2, 4.6),
    ]
    # cut_len = 7 (from index 0 to 7), match_len = 3 → ratio = 3/7 ≈ 0.43 < 0.5
    ranges, candidates = detect_retakes(words, min_retake_words=3, min_match_ratio=0.5)
    assert ranges == []
    assert any(not c.kept for c in candidates)


def test_single_word_difference_does_not_truncate_match():
    """An isolated reinflected word mid-repeat must not halt the greedy match.

    Regression: 'the whole prompt needed to be fixed' → 'the whole prompt needs
    to be fixed'. The lone 'needed'/'needs' difference previously stopped the
    extension at match_len=3, giving ratio 3/7=0.43 < 0.5 so the failed take
    survived. Skipping one mismatched word recovers match_len=6 (ratio 0.86).
    """
    words = [
        # first (flubbed) take
        _w("the",    0.0, 0.2),
        _w("whole",  0.3, 0.5),
        _w("prompt", 0.6, 0.9),
        _w("needed", 1.0, 1.3),   # differs from second take
        _w("to",     1.4, 1.5),
        _w("be",     1.6, 1.7),
        _w("fixed",  1.8, 2.1),
        # second (kept) take
        _w("the",    2.5, 2.7),
        _w("whole",  2.8, 3.0),
        _w("prompt", 3.1, 3.4),
        _w("needs",  3.5, 3.8),
        _w("to",     3.9, 4.0),
        _w("be",     4.1, 4.2),
        _w("fixed",  4.3, 4.6),
    ]
    ranges, candidates = detect_retakes(words, min_retake_words=3, min_match_ratio=0.5)
    assert len(ranges) == 1
    assert ranges[0][0] == pytest.approx(0.0)
    assert ranges[0][1] == pytest.approx(2.5)


def test_truncated_middle_take_does_not_strand_first_take_head():
    """Three takes where the middle one is a truncated/abandoned fragment.

    Regression (claude-1m-context-window-trap): the speaker said the full phrase,
    abandoned a short restart, then said the full phrase again (the keeper):
        take 1: "memory having to hold a value for every token at once" (complete)
        take 2: "memory having to hold a"                               (abandoned)
        take 3: "memory having to hold a value for every token at once" (kept)

    Consecutive-only pairing compares take 1 → take 2. Because take 2 truncates
    after 5 words while take 1 runs 11, the match ratio is 5/11 = 0.45 < 0.50, so
    that pair is skipped and take 1's leading "memory having to" survives —
    producing a stutter against take 3. Pairing take 1 directly against the final
    occurrence (take 3) scores 11/16 = 0.69 and cuts take 1 entirely.
    """
    words = [
        # take 1 — complete (indices 0-10)
        _w("memory", 0.0, 0.4), _w("having", 0.5, 0.7), _w("to", 0.8, 0.9),
        _w("hold", 1.0, 1.2), _w("a", 1.3, 1.4), _w("value", 1.5, 1.8),
        _w("for", 1.9, 2.0), _w("every", 2.1, 2.3), _w("token", 2.4, 2.7),
        _w("at", 2.8, 2.9), _w("once", 3.0, 3.3),
        # take 2 — abandoned after 5 words (indices 11-15)
        _w("memory", 4.0, 4.4), _w("having", 4.5, 4.7), _w("to", 4.8, 4.9),
        _w("hold", 5.0, 5.2), _w("a", 5.3, 5.4),
        # take 3 — the keeper (indices 16-27)
        _w("memory", 6.0, 6.4), _w("having", 6.5, 6.7), _w("to", 6.8, 6.9),
        _w("hold", 7.0, 7.2), _w("a", 7.3, 7.4), _w("value", 7.5, 7.8),
        _w("for", 7.9, 8.0), _w("every", 8.1, 8.3), _w("token", 8.4, 8.7),
        _w("at", 8.8, 8.9), _w("once", 9.0, 9.3), _w("done", 9.4, 9.8),
    ]
    ranges, _ = detect_retakes(words, min_retake_words=3, min_match_ratio=0.5)
    # Both earlier takes collapse into a single cut ending at take 3's start.
    assert len(ranges) == 1
    assert ranges[0][0] == pytest.approx(0.0)   # cut begins at take 1's first word
    assert ranges[0][1] == pytest.approx(6.0)   # cut ends at take 3 (the keeper)


def test_transposed_words_still_detected_without_lowering_min_words():
    """A retake where two adjacent words are transposed is still caught at mrw=3.

    Regression (claude-1m-context-window-trap outro): the aligner swapped an
    adjacent pair, so the two otherwise-identical takes share no exact 3-gram:
        take 1: "follow for AI more fundamentals"   (flubbed; AI/more swapped)
        take 2: "follow for more AI fundamentals"   (keeper)
    Swap-variant seeding lets the takes collide on the n-gram spanning the swap,
    and backward extension recovers the leading "follow" the interior seed skips,
    so the whole flubbed take is cut without dropping min_retake_words to 2.
    """
    words = [
        # take 1 — transposed "AI"/"more" (indices 0-4)
        _w("follow", 0.0, 0.3), _w("for", 0.4, 0.6), _w("AI", 0.7, 0.9),
        _w("more", 0.9, 1.1), _w("fundamentals", 1.2, 1.6),
        # take 2 — the keeper, correct order (indices 5-9)
        _w("follow", 8.0, 8.3), _w("for", 8.4, 8.6), _w("more", 8.7, 8.9),
        _w("AI", 9.0, 9.2), _w("fundamentals", 9.3, 9.8),
    ]
    ranges, _ = detect_retakes(words, min_retake_words=3, max_retake_gap_s=12.0, min_match_ratio=0.5)
    assert len(ranges) == 1
    assert ranges[0][0] == pytest.approx(0.0)   # cut begins at take 1's "follow"
    assert ranges[0][1] == pytest.approx(8.0)   # cut ends at take 2 (the keeper)


def test_three_takes_leading_divergence_snaps_to_take_boundaries():
    """Three takes sharing a core phrase but diverging at the head, separated by
    real (>take_boundary_s) silences — the 'no particular virus' billion-laughs cluster.

        take A: "with no particular virus or stolen passwords instead it was just a few valid xml"
        take B: "see there was no  virus or stolen password  instead it was just a few lines of valid xml"
        take C: "see there was no  virus or stolen password  instead it was just a few lines of completely valid xml"  (keeper)

    The pairwise matcher anchors on the shared core, so the A→B cut ends mid-take-B
    (its tail "…just a few lines of valid xml" matches take C and is stranded as a
    duplicate via the min-end merge) and take A's unmatched head "with no particular"
    survives as a stutter. Boundary snapping pulls the cut start back to take A's
    first word and pushes the end forward to take C's first word (both across the
    surrounding silences), cutting takes A and B entirely and keeping only take C.
    """
    # A neutral kept sentence precedes take A across a real silence (as in the real
    # clip, where "…a few valid xml pages." sits before the cluster). The leading
    # silence is what lets the START snap find take A's boundary.
    segments = [
        "here is a totally different opening sentence",                                                  # kept lead-in
        "with no particular virus or stolen passwords instead it was just a few valid xml",              # take A
        "see there was no virus or stolen password instead it was just a few lines of valid xml",        # take B
        "see there was no virus or stolen password instead it was just a few lines of completely valid xml",  # take C (keeper)
    ]
    words, seg_starts, t = [], [], 1.0
    for si, seg in enumerate(segments):
        if si:
            t += 3.0  # real silence between segments (> take_boundary_s default of 2.0)
        seg_starts.append(t)
        for wi, tok in enumerate(seg.split()):
            if wi:
                t += 0.05
            words.append(_w(tok, t, t + 0.15))
            t += 0.15
    ranges, _ = detect_retakes(words, min_retake_words=3, max_retake_gap_s=20.0, min_match_ratio=0.5)
    assert len(ranges) == 1
    assert ranges[0][0] == pytest.approx(seg_starts[1])   # cut begins at take A's first word
    assert ranges[0][1] == pytest.approx(seg_starts[3])   # cut ends at take C (the keeper)


def test_consecutive_mismatches_still_stop_extension():
    """A run of mismatches beyond max_retake_skip means genuine divergence → no cut."""
    words = [
        _w("things",  0.0, 0.3),
        _w("like",    0.4, 0.7),
        _w("cyber",   0.8, 1.1),
        _w("attacks", 1.2, 1.6),   # two consecutive differing words ...
        _w("are",     1.7, 1.9),   # ... exceed max_retake_skip=1
        _w("serious", 2.0, 2.4),
        _w("risks",   2.5, 2.9),
        _w("things",  3.0, 3.3),
        _w("like",    3.4, 3.7),
        _w("cyber",   3.8, 4.1),
        _w("defense", 4.2, 4.6),
        _w("matters", 4.7, 5.1),
        _w("today",   5.2, 5.6),
    ]
    ranges, _ = detect_retakes(words, min_retake_words=3, min_match_ratio=0.5, max_retake_skip=1)
    assert ranges == []
