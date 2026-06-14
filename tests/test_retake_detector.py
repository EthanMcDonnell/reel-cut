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
