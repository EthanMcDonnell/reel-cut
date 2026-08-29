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


# ---------------------------------------------------------------------------
# Aborted restarts — a short opener that trails off ('...') and is immediately
# re-said from the same prefix. Too short to seed the positional matcher, too
# little content overlap for the reworded pass; caught by _detect_aborted_restarts.
# ---------------------------------------------------------------------------

def test_aborted_restart_two_word_prefix():
    """Real 'It's called Amazon… It's called Magic Pocket…' abort (dropbox clip).

    Shares only 'It's called' (2 words) before diverging on the first content word,
    so neither the n-gram nor the reworded pass sees it. The failed opener must be cut
    from its take start (62.322) to the restart (64.763), leaving the keeper intact.
    """
    words = [
        _w("boring.",    61.538, 61.840),   # kept lead-in sentence, ends the prior take
        _w("It's",       62.322, 62.444),   # ── aborted head ──
        _w("called",     62.464, 62.648),
        _w("Amazon...",  62.729, 63.054),   # trail-off
        _w("It's",       64.763, 64.883),   # ── restart / keeper ──
        _w("called",     64.903, 65.104),
        _w("Magic",      65.145, 65.386),
        _w("Pocket",     65.446, 65.748),
        _w("and",        65.828, 65.909),
        _w("it",         65.949, 65.989),
        _w("holds",      66.050, 66.231),
        _w("multiple",   66.331, 66.733),
        _w("exabytes",   66.935, 67.478),
        _w("data.",      67.659, 67.920),
    ]
    ranges, _ = detect_retakes(words, min_retake_words=3)
    assert len(ranges) == 1
    cut_start, cut_end = ranges[0]
    assert cut_start == pytest.approx(62.322)
    assert cut_end == pytest.approx(64.763)


def test_aborted_restart_disabled():
    """detect_aborted=False leaves the short abort uncut (the other passes still miss it)."""
    words = [
        _w("boring.",    61.538, 61.840),
        _w("It's",       62.322, 62.444),
        _w("called",     62.464, 62.648),
        _w("Amazon...",  62.729, 63.054),
        _w("It's",       64.763, 64.883),
        _w("called",     64.903, 65.104),
        _w("Magic",      65.145, 65.386),
        _w("Pocket",     65.446, 65.748),
        _w("data.",      67.659, 67.920),
    ]
    ranges, _ = detect_retakes(words, min_retake_words=3, detect_aborted=False)
    assert ranges == []


def test_emphasis_not_aborted_restart():
    """A completed short sentence re-said for emphasis (no trail-off) is NOT a retake.

    'I love it.' ends with a period, not an ellipsis — the speaker finished the thought.
    Without the trail-off anchor, sharing a 2-word prefix with the next sentence is not
    enough to cut it."""
    words = [
        _w("I",     0.0, 0.2),
        _w("love",  0.3, 0.5),
        _w("it.",   0.6, 0.9),
        _w("I",     1.2, 1.4),
        _w("love",  1.5, 1.7),
        _w("this",  1.8, 2.0),
        _w("whole", 2.1, 2.3),
        _w("thing.", 2.4, 2.7),
    ]
    ranges, _ = detect_retakes(words, min_retake_words=3)
    assert ranges == []


def test_trail_off_continuation_not_aborted_restart():
    """A trail-off that CONTINUES the thought (no re-say of the opening) is not a retake.

    'The files sit on ordinary spinning… hard drives…' trails off then keeps going;
    the words after the ellipsis don't repeat the take's opening, so nothing is cut."""
    words = [
        _w("The",       0.0, 0.2),
        _w("files",     0.3, 0.5),
        _w("sit",       0.6, 0.8),
        _w("on",        0.9, 1.0),
        _w("ordinary",  1.1, 1.4),
        _w("spinning...", 1.5, 1.9),
        _w("hard",      2.1, 2.3),
        _w("drives.",   2.4, 2.7),
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


# ---------------------------------------------------------------------------
# Gap vs span: max_retake_gap_s bounds the silence BETWEEN takes, not take length
# ---------------------------------------------------------------------------

def _long_back_to_back_retake():
    """Two takes of one long (~14s) sentence, recorded back-to-back (0.2s pause).

    The take body is far longer than max_retake_gap_s, but the takes themselves are
    adjacent. The seed n-gram ends ~1.5s in (words[2]); under the old guard the
    'gap' was measured seed-end → take 2 = 12.7s and the take was wrongly rejected.
    """
    return [
        _w("the",    0.0,  0.5),
        _w("fix",    0.6,  1.0),
        _w("is",     1.1,  1.5),   # seed = the/fix/is ends here, ~1.5s into take 1
        _w("really", 1.6,  3.0),
        _w("quite",  3.1,  6.0),
        _w("simple", 6.1,  10.0),
        _w("here",   10.1, 14.0),  # take 1 spans 0.0 → 14.0
        _w("the",    14.2, 14.7),  # take 2 starts after a 0.2s pause
        _w("fix",    14.8, 15.2),
        _w("is",     15.3, 15.7),
        _w("really", 15.8, 17.0),
        _w("quite",  17.1, 20.0),
        _w("simple", 20.1, 24.0),
        _w("here",   24.1, 28.0),
    ]


def test_long_back_to_back_retake_not_rejected_by_proximity():
    """A long sentence re-recorded back-to-back is cut even though its body exceeds
    max_retake_gap_s — the gap is measured between takes (0.2s), not across take 1."""
    words = _long_back_to_back_retake()
    ranges, _ = detect_retakes(words, min_retake_words=3, max_retake_gap_s=12.0, min_match_ratio=0.5)
    assert len(ranges) == 1
    assert ranges[0][0] == pytest.approx(0.0)    # cut begins at take 1's first word
    assert ranges[0][1] == pytest.approx(14.2)   # cut ends at take 2 (the keeper)


def test_span_cap_discards_runaway_cut_independent_of_gap():
    """The span filter is governed by max_retake_span_s, not max_retake_gap_s: with a
    tight span cap the same adjacent-take cut (14.2s span) is dropped as a safety net,
    even though the inter-take gap easily passes max_retake_gap_s."""
    words = _long_back_to_back_retake()
    ranges, _ = detect_retakes(
        words, min_retake_words=3, max_retake_gap_s=20.0, min_match_ratio=0.5,
        max_retake_span_s=10.0,
    )
    assert ranges == []


# ---------------------------------------------------------------------------
# Real-clip regression: boundary snapping must not swallow a kept sentence that
# flows into the next failed take with < take_boundary_s of silence.
# ---------------------------------------------------------------------------

# Exact words + timestamps from the billion-laughs clip
# (Teleprompter-2026-24-06_00-16-42, debug.4.post-vad), 37.0s–110.0s. Three
# distinct retake clusters — the "no virus / stolen password / valid xml" cluster,
# the "so how does … that tiny do that much damage" cluster, and the "you define a
# word once and reuse it" cluster — interleaved with one UNIQUE kept sentence,
# "It comes down to a normal XML feature called entities, which are shortcuts."
# (92.951–97.32s). That sentence is spoken straight into the following "You define…"
# failed take with only a 0.72s gap (< take_boundary_s), so the START back-snap of
# the "you define" cut walks its start backward across the whole kept sentence to the
# real boundary at "So" @89.41, and the re-merge fuses all three cuts into one ~57s
# range (49.94→107.15) that deletes the kept sentence.
_BILLION_LAUGHS_RETAKE_REGION = [
    ('and', 37.118, 37.239), ('crash.', 37.339, 37.72), ('No', 38.44, 38.601), ('virus,', 38.681, 39.163),
    ('no', 39.464, 39.605), ('stolen', 39.705, 40.127), ('password,', 40.187, 40.81), ('just', 41.111, 41.312),
    ('a', 41.372, 41.392), ('few', 41.492, 41.713), ('valid', 41.814, 42.215), ('xml', 42.476, 42.998),
    ('pages.', 43.039, 43.34), ('With', 49.941, 50.081), ('no', 50.121, 50.262), ('particular', 50.322, 50.824),
    ('virus', 50.864, 51.245), ('or', 51.365, 51.445), ('stolen', 51.526, 51.967), ('passwords,', 52.027, 52.669),
    ('instead', 53.01, 53.592), ('it', 53.913, 53.973), ('was', 53.993, 54.114), ('just', 54.154, 54.334),
    ('a', 54.395, 54.415), ('few', 54.535, 54.776), ('valid', 54.84, 55.5), ('xml.', 55.097, 55.338),
    ('See,', 61.784, 61.905), ('there', 61.925, 62.046), ('was', 62.066, 62.167), ('no', 62.207, 62.328),
    ('virus', 62.408, 62.832), ('or', 62.892, 62.973), ('stolen', 63.033, 63.396), ('password.', 63.456, 63.92),
    ('Instead,', 64.38, 64.863), ('it', 65.204, 65.265), ('was', 65.305, 65.446), ('just', 65.486, 65.687),
    ('a', 65.727, 65.768), ('few', 65.908, 66.23), ('lines', 66.331, 66.733), ('of', 66.833, 66.914),
    ('valid', 67.034, 67.477), ('XML.', 67.758, 68.08), ('See,', 74.284, 74.404), ('there', 74.425, 74.545),
    ('was', 74.566, 74.666), ('no', 74.707, 74.848), ('virus', 74.928, 75.392), ('or', 75.492, 75.593),
    ('stolen', 75.654, 76.077), ('password.', 76.117, 76.52), ('Instead,', 77.06, 77.543), ('it', 77.643, 77.703),
    ('was', 77.744, 77.884), ('just', 77.925, 78.166), ('a', 78.226, 78.246), ('few', 78.367, 78.648),
    ('lines', 78.688, 79.05), ('of', 79.111, 79.191), ('completely', 79.271, 80.035), ('valid', 80.116, 80.518),
    ('XML.', 80.699, 80.96), ('So,', 81.94, 81.98), ('how', 82.021, 82.102), ('does', 82.123, 82.285),
    ('something', 82.326, 82.651), ('that...', 82.671, 82.793), ('So', 83.601, 83.725), ('how', 83.766, 83.849),
    ('does', 83.89, 84.014), ('that?', 84.034, 84.158), ('So', 89.41, 89.531), ('how', 89.572, 89.693),
    ('does', 89.713, 89.834), ('something', 89.854, 90.116), ('that', 90.157, 90.359), ('tiny', 90.399, 90.742),
    ('do', 90.782, 90.923), ('that', 90.984, 91.145), ('much', 91.206, 91.448), ('damage?', 91.508, 91.69),
    ('It', 92.951, 93.011), ('comes', 93.071, 93.311), ('down', 93.371, 93.612), ('to', 93.752, 93.873),
    ('a', 93.913, 93.953), ('normal', 94.053, 94.414), ('XML', 94.574, 94.975), ('feature', 95.035, 95.356),
    ('called', 95.416, 95.636), ('entities,', 95.736, 96.157), ('which', 96.518, 96.658), ('are', 96.719, 96.799),
    ('shortcuts.', 96.839, 97.32), ('You', 98.04, 98.141), ('define', 98.181, 98.503), ('a', 98.543, 98.563),
    ('word', 98.623, 98.925), ('once', 99.387, 99.568), ('and', 99.87, 99.971), ('reuse', 100.031, 100.433),
    ('it', 100.493, 100.534), ('anywhere', 100.674, 101.016), ('so', 101.358, 101.539), ('often.', 101.56, 101.68),
    ('You', 107.15, 107.251), ('define', 107.271, 107.553), ('a', 107.574, 107.614), ('word', 107.634, 107.856),
    ('once,', 107.997, 108.178), ('and', 108.461, 108.562), ('re', 108.663, 108.844), ('-use', 108.864, 109.106),
    ('it', 109.167, 109.207), ('anywhere.', 109.348, 109.57),
]


def test_real_clip_snap_does_not_swallow_kept_sentence_between_clusters():
    """Regression (billion-laughs): a unique kept sentence sitting between two retake
    clusters, run into the next failed take by a sub-take_boundary_s gap, must survive.

    "It comes down to a normal XML feature called entities, which are shortcuts."
    (92.951–97.32s) is not a retake of anything. Boundary snapping must not absorb it.
    """
    words = [_w(t, s, e) for t, s, e in _BILLION_LAUGHS_RETAKE_REGION]
    ranges, _ = detect_retakes(
        words, min_retake_words=3, max_retake_gap_s=12.0, min_match_ratio=0.5,
        max_retake_bridge_s=1.0, max_retake_span_s=60.0,
    )
    # No cut may cover any word of the kept sentence (92.951s → 97.32s).
    kept_start, kept_end = 92.951, 97.32
    swallowed = [
        (s, e) for s, e in ranges if s < kept_end and e > kept_start
    ]
    assert not swallowed, f"kept sentence swallowed by cut(s): {swallowed}"


# ---------------------------------------------------------------------------
# Real-clip regression: the START back-snap must not absorb a preamble the keeper
# take has no counterpart for.
# ---------------------------------------------------------------------------

# Exact words + timestamps from the canva-session-revocations-s3 clip
# (856D0E66-E505-4529-9AC1-E30DCF76FFDC, debug.5.timeline), 66.0s–100.0s.
# Three takes of the "older ones don't matter" beat. The FIRST take opens with a
# scripted sentence that is never re-said — "A booting gateway grabs only the last
# 12 hours," — spoken straight into the matched core with only a 0.58s breath, so
# "older" @76.895 is not a take boundary and the back-snap walks to "A" @73.261.
_CANVA_TWELVE_HOURS_REGION = [
    ('So', 66.82, 66.921), ("here's", 66.961, 67.162), ('the', 67.182, 67.262), ('clever', 67.282, 67.543),
    ('part,', 67.563, 67.824), ('they', 68.225, 68.406), ('moved', 68.466, 68.727), ('the', 68.747, 68.847),
    ('list', 68.908, 69.168), ('into', 69.309, 69.49), ('S3,', 69.771, 70.292), ('chopped', 70.674, 70.975),
    ('into', 71.015, 71.195), ('timestamp', 71.296, 71.978), ('chunks.', 72.078, 72.48), ('A', 73.261, 73.301),
    ('booting', 73.381, 73.763), ('gateway', 73.843, 74.265), ('grabs', 74.405, 74.706), ('only', 74.807, 74.988),
    ('the', 75.048, 75.128), ('last', 75.168, 75.449), ('12', 75.44, 75.8), ('hours,', 75.911, 76.313),
    ('older', 76.895, 77.116), ('ones', 77.236, 77.437), ("don't", 77.578, 77.799), ('matter.', 77.879, 78.14),
    ('Older', 82.786, 82.988), ('ones', 83.11, 83.312), ("don't", 83.434, 83.656), ('matter.', 83.738, 83.94),
    ('Since', 84.421, 84.622), ('every', 84.844, 85.066), ('cookie', 85.167, 85.53), ('refreshes', 85.631, 86.216),
    ('by', 86.297, 86.458), ('then.', 86.519, 86.66), ('Older', 90.971, 91.172), ('ones', 91.252, 91.412),
    ("don't", 91.453, 91.653), ('matter,', 91.673, 91.994), ('since', 92.215, 92.435), ('every', 92.596, 92.816),
    ('cookie', 92.896, 93.277), ('usually', 93.759, 94.16), ('refreshes', 94.24, 94.761), ('by', 94.821, 94.962),
    ('then,', 95.022, 95.243), ('and', 95.784, 95.884), ('refreshes', 95.944, 96.466), ('get', 96.546, 96.707),
    ('checked', 96.807, 97.128), ('against', 97.168, 97.469), ('the', 97.549, 97.629), ('database.', 97.669, 97.97),
    ('Each', 99.32, 99.461), ('revocation', 99.521, 100.062),
]


def test_real_clip_snap_does_not_absorb_preamble_keeper_never_re_said():
    """Regression (canva-session-revocations-s3): keep the LAST take — but the cut for
    it must not reach back over a sentence that take never re-said.

    Three takes of "older ones don't matter…"; the last is the keeper (correct). The
    first opens with "A booting gateway grabs only the last 12 hours," — a scripted
    sentence present in no other take. The keeper begins exactly on the matched core
    ("Older ones don't matter"), so it has no head of its own for those words to be a
    divergent restatement OF; absorbing them deletes the 12-hour window outright and
    strands "Older ones" without a referent.
    """
    words = [_w(t, s, e) for t, s, e in _CANVA_TWELVE_HOURS_REGION]
    ranges, _ = detect_retakes(
        words, min_retake_words=3, max_retake_gap_s=12.0, min_match_ratio=0.5,
        max_retake_bridge_s=1.0, max_retake_span_s=60.0, min_reword_overlap=0.6,
    )
    assert len(ranges) == 1
    cut_start, cut_end = ranges[0]
    assert cut_start == pytest.approx(76.895)   # cut opens at "older", NOT "A" @73.261
    assert cut_end == pytest.approx(90.971)     # …and ends on the keeper's first word
    # the unique lead-in survives in full
    assert not any(s < 76.3 and e > 73.2 for s, e in ranges)


def test_real_clip_first_reworded_take_is_cut():
    """Regression (billion-laughs): the first take of the cluster is a REWORDED failed
    take and must still be cut.

        take A (38.44–43.34): "No virus, no stolen password, just a few valid xml pages."
        take B+ (49.94→):     "(With no particular / See there was no) virus or stolen
                               password … instead it was just a few lines of … valid XML."

    Take A shares only "just a few valid xml" with the dense literal core the later
    takes repeat, so the pairwise matcher's ratio gate (0.31 < 0.50) rejects it and it
    survives. It is the same intended line, re-recorded, and should be cut down to the
    final keeper take like the rest of the cluster.
    """
    words = [_w(t, s, e) for t, s, e in _BILLION_LAUGHS_RETAKE_REGION]
    ranges, _ = detect_retakes(
        words, min_retake_words=3, max_retake_gap_s=12.0, min_match_ratio=0.5,
        max_retake_bridge_s=1.0, max_retake_span_s=60.0,
    )
    # Some cut must cover take A (38.44s → 43.34s).
    take_a_start, take_a_end = 38.44, 43.34
    covered = any(s <= take_a_start and e >= take_a_end for s, e in ranges)
    assert covered, f"reworded take A (38.44–43.34s) not cut; ranges={ranges}"


# ---------------------------------------------------------------------------
# Sentence-overlap pass (reworded takes the positional matcher can't see)
# ---------------------------------------------------------------------------

def test_reworded_take_cut_by_sentence_overlap():
    """A take re-recorded with different word order/connectives shares no long
    contiguous run (so the positional pass misses it) but most of its content words —
    the sentence-overlap pass cuts the failed take down to the reworded keeper."""
    words = [
        _w("The", 0.0, 0.3), _w("server", 0.4, 0.9), _w("crashed", 1.0, 1.5),
        _w("completely", 1.6, 2.2), _w("yesterday.", 2.3, 2.9),
        # 1s gap, same line reworded (kept)
        _w("The", 3.9, 4.2), _w("server", 4.3, 4.8), _w("totally", 4.9, 5.4),
        _w("crashed", 5.5, 6.0), _w("yesterday.", 6.1, 6.7),
    ]
    ranges, _ = detect_retakes(words, min_retake_words=3, max_retake_gap_s=12.0, min_match_ratio=0.5)
    assert len(ranges) == 1
    assert ranges[0][0] == pytest.approx(0.0)   # cut begins at the failed take
    assert ranges[0][1] == pytest.approx(3.9)   # …and ends at the keeper's first word


def test_distinct_sentences_sharing_glue_words_not_cut():
    """Two genuinely different sentences that share only common/glue words must not be
    treated as a retake — the stopword filter keeps the overlap near zero."""
    words = [
        _w("First", 0.0, 0.4), _w("configure", 0.5, 1.0), _w("the", 1.1, 1.3), _w("server.", 1.4, 1.9),
        _w("Then", 2.9, 3.3), _w("restart", 3.4, 3.9), _w("the", 4.0, 4.2), _w("database.", 4.3, 4.8),
    ]
    ranges, _ = detect_retakes(words, min_retake_words=3, max_retake_gap_s=12.0, min_match_ratio=0.5)
    assert ranges == []


def test_reworded_pass_preserves_unique_sentence_between_take_and_reprise():
    """A unique sentence sitting between a reworded failed take and its reprise must
    survive: the cut covers only the failed take (up to the next sentence), never the
    intervening kept content."""
    # Content overlaps but no 3 consecutive words match, so only the sentence-overlap
    # pass (not the positional matcher) can pair the take with its reprise.
    words = [
        # failed take
        _w("Memory", 0.0, 0.4), _w("leaked", 0.5, 0.9), _w("because", 1.0, 1.5),
        _w("pointers", 1.6, 2.1), _w("dangled.", 2.2, 2.7),
        # unique kept sentence, only sentence punctuation separates it (<2s gaps)
        _w("Birds", 3.0, 3.4), _w("fly", 3.5, 3.8), _w("high", 3.9, 4.3), _w("above.", 4.4, 4.9),
        # reworded reprise (kept)
        _w("Pointers", 5.2, 5.7), _w("dangled", 5.8, 6.2), _w("so", 6.3, 6.5),
        _w("memory", 6.6, 7.0), _w("leaked.", 7.1, 7.6),
    ]
    ranges, _ = detect_retakes(words, min_retake_words=3, max_retake_gap_s=12.0, min_match_ratio=0.5)
    assert len(ranges) == 1
    assert ranges[0][0] == pytest.approx(0.0)
    assert ranges[0][1] == pytest.approx(3.0)   # ends at the unique sentence's first word
    # no cut overlaps the unique sentence "Birds fly high above." (3.0s–4.9s)
    assert not any(s < 4.9 and e > 3.0 for s, e in ranges)


def test_number_split_retake_is_cut():
    """A false start and its clean retake sharing a spoken number must be cut.

    Regression: _normalize used to erase digits, so "500" → "". That barred every
    n-gram spanning the number from seeding and halted the backward extension the
    instant it hit the empty token. The only seedable phrase ("kafka brokers to") then
    sat *after* the number and matched just 3 of 7 words (0.43 < 0.5 threshold),
    leaving the false start "Reddit moved 500 Kafka brokers to re…" uncut. Keeping the
    digits lets "reddit moved 500 …" match the keeper end-to-end (6/7 = 0.86)."""
    words = [
        # false start, cut off at "to re..."
        _w("Reddit", 16.9, 17.1), _w("moved", 17.2, 17.4), _w("500", 17.5, 18.0),
        _w("Kafka", 18.0, 18.4), _w("brokers", 18.4, 18.8), _w("to", 18.9, 19.0),
        _w("re...", 19.1, 19.4),
        # clean retake (kept), begins after a ~5.5s pause
        _w("Reddit", 24.9, 25.2), _w("moved", 25.2, 25.4), _w("500", 25.5, 26.0),
        _w("Kafka", 26.0, 26.3), _w("brokers", 26.3, 26.6), _w("to", 26.7, 26.8),
        _w("Kubernetes", 26.8, 27.4), _w("without", 27.4, 27.7), _w("a", 27.7, 27.75),
        _w("single", 27.8, 28.2), _w("user", 28.5, 28.8), _w("noticing.", 28.9, 29.1),
    ]
    ranges, _ = detect_retakes(words, min_retake_words=3, max_retake_gap_s=12.0, min_match_ratio=0.5)
    assert len(ranges) == 1
    assert ranges[0][0] == pytest.approx(16.9)   # cut begins at the false start
    assert ranges[0][1] == pytest.approx(24.9)   # …and ends at the keeper's first word


def test_mid_sentence_restart_keeps_unique_lead_in():
    """A retake that restarts MID-sentence must cut only the flubbed tail, not the
    unique clause before it.

    "…turning an impossible refactor into a simple code" → "into a simple config
    change": the matcher correctly anchors "into a simple" and cuts just the flubbed
    tail. But the START snap used to pull the cut back to the sentence's first word
    ("Now" — a take boundary after the previous sentence's period + silence), swallowing
    the unique lead-in and stranding the keeper as a subjectless "into a simple config
    change". The preamble (the whole sentence body) is far longer than the keeper
    fragment, so the snap must bail and leave the lead-in kept."""
    words = [
        # prior kept sentence: its period + the >2s gap makes "Now" a take boundary
        _w("They", 0.0, 0.3), _w("fixed", 0.4, 0.8), _w("the", 0.9, 1.0), _w("names.", 1.1, 1.6),
        # unique kept lead-in (one sentence, no internal sentence-end)
        _w("Now", 4.0, 4.2), _w("Reddit", 4.3, 4.6), _w("owned", 4.7, 5.0), _w("the", 5.1, 5.2),
        _w("names,", 5.3, 5.7), _w("turning", 5.8, 6.2), _w("an", 6.3, 6.4),
        _w("impossible", 6.5, 7.1), _w("refactor", 7.2, 7.8),
        # flubbed tail (to be cut)
        _w("into", 7.9, 8.1), _w("a", 8.2, 8.3), _w("simple", 8.4, 8.8), _w("code.", 8.9, 9.3),
        # mid-sentence restart / keeper — begins right after the flub's sentence-end
        _w("into", 9.6, 9.8), _w("a", 9.9, 10.0), _w("simple", 10.1, 10.5),
        _w("config", 10.6, 11.0), _w("change.", 11.1, 11.6),
        # next sentence (a take boundary via the sentence-end above)
        _w("Then", 12.0, 12.3), _w("the", 12.4, 12.5), _w("best", 12.6, 12.9), _w("part.", 13.0, 13.4),
    ]
    ranges, _ = detect_retakes(words, min_retake_words=3, max_retake_gap_s=12.0, min_match_ratio=0.5)
    assert len(ranges) == 1
    cut_start, cut_end = ranges[0]
    assert cut_start == pytest.approx(7.9)   # cut begins at the flubbed "into", NOT "Now"
    assert cut_end == pytest.approx(9.6)     # …and ends at the keeper's first word
    # the unique lead-in "Now Reddit owned the names, turning an impossible refactor" survives
    assert not any(s < 7.8 and e > 4.0 for s, e in ranges)


def test_different_numbers_not_treated_as_same_word():
    """Digits are kept for matching but distinct numbers must not falsely match: two
    unrelated sentences that differ only in their numbers share no repeated content and
    stay uncut (guards against a naive number→placeholder normalization)."""
    words = [
        _w("We", 0.0, 0.2), _w("scaled", 0.3, 0.7), _w("to", 0.8, 0.9), _w("500", 1.0, 1.4), _w("nodes.", 1.5, 2.0),
        _w("They", 3.0, 3.2), _w("dropped", 3.3, 3.7), _w("to", 3.8, 3.9), _w("250", 4.0, 4.4), _w("cores.", 4.5, 5.0),
    ]
    ranges, _ = detect_retakes(words, min_retake_words=3, max_retake_gap_s=12.0, min_match_ratio=0.5)
    assert ranges == []


def test_end_snap_does_not_swallow_the_keeper():
    """Regression (utf-8-character-encoding, ~2:32-2:55): the END boundary snap deleted
    the final take instead of stopping at it.

        take 1: "-8 skips that problem because each byte marks its own place,
                 so minimum can be 1 byte."                          (trailed off)
        take 2: "UTF -8 skips this problem altogether because each byte marks its
                 own place, so it can be minimum only 1 byte, but still scales up
                 to 4 bytes if needed."                              (keeper)

    The takes diverge right before the shared core ("that problem" vs "this problem
    altogether"), so the backward extension stalls and the cut ends on "because" —
    *inside* take 2. That word has no take boundary in front of it, so the END snap
    walked forward to the next boundary and cut take 2 in full: the whole script line
    vanished from the video, with no earlier take left to carry it.

    The absorbed material is only ever safe to swallow when a later take re-says it.
    Nothing after take 2 repeats it, so the cut must instead end back at take 2's
    first word.
    """
    words = [
        # a kept lead-in, so the cut has a take boundary to open against
        _w("nothing", 0.0, 0.4), _w("here", 0.5, 0.9), _w("repeats.", 1.0, 1.5),
        # take 1 — trails off (starts after a real silence)
        _w("-8", 5.0, 5.4), _w("skips", 5.5, 5.9), _w("that", 6.0, 6.2),
        _w("problem", 6.3, 6.7), _w("because", 6.8, 7.2), _w("each", 7.3, 7.6),
        _w("byte", 7.7, 8.0), _w("marks", 8.1, 8.4), _w("its", 8.5, 8.7),
        _w("own", 8.8, 9.0), _w("place,", 9.1, 9.5), _w("so", 9.6, 9.8),
        _w("minimum", 9.9, 10.3), _w("can", 10.4, 10.6), _w("be", 10.7, 10.9),
        _w("1", 11.0, 11.2), _w("byte.", 11.3, 11.7),
        # take 2 — the keeper, after a real silence; head diverges from take 1's
        _w("UTF", 17.0, 17.3), _w("-8", 17.4, 17.7), _w("skips", 17.8, 18.2),
        _w("this", 18.3, 18.5), _w("problem", 18.6, 19.0),
        _w("altogether", 19.1, 19.6), _w("because", 19.7, 20.1),
        _w("each", 20.2, 20.5), _w("byte", 20.6, 20.9), _w("marks", 21.0, 21.3),
        _w("its", 21.4, 21.6), _w("own", 21.7, 21.9), _w("place,", 22.0, 22.4),
        _w("so", 22.5, 22.7), _w("it", 22.8, 22.9), _w("can", 23.0, 23.2),
        _w("be", 23.3, 23.5), _w("minimum", 23.6, 24.0), _w("only", 24.1, 24.5),
        _w("1", 24.6, 24.8), _w("byte,", 24.9, 25.3), _w("but", 25.4, 25.6),
        _w("still", 25.7, 26.0), _w("scales", 26.1, 26.5), _w("up", 26.6, 26.8),
        _w("to", 26.9, 27.0), _w("4", 27.1, 27.3), _w("bytes", 27.4, 27.7),
        _w("if", 27.8, 27.9), _w("needed.", 28.0, 28.4),
        # the next, unrelated sentence
        _w("Nothing", 30.0, 30.4), _w("in", 30.5, 30.7), _w("the", 30.8, 30.9),
        _w("file", 31.0, 31.4), _w("says", 31.5, 31.9), _w("which.", 32.0, 32.5),
    ]
    ranges, _ = detect_retakes(
        words, min_retake_words=3, max_retake_gap_s=12.0, min_match_ratio=0.5,
    )
    assert len(ranges) == 1
    assert ranges[0][0] == pytest.approx(5.0)    # cut begins at take 1's first word
    assert ranges[0][1] == pytest.approx(17.0)   # cut ends at take 2 — the keeper


def test_repeat_with_no_pause_between_takes_is_not_cut():
    """A phrase repeated inside one continuous sentence is parallel phrasing, not a
    retake — re-recording a line means stopping first.

    Regression (billion-laughs-attack): "one entity as 10 copies of lull, the next as
    10 copies of that" scored 0.57, cleared min_match_ratio, and lost its first half.
    """
    words = [
        _w("You", 0.0, 0.2), _w("define", 0.3, 0.6), _w("one", 0.7, 0.8),
        _w("entity", 0.9, 1.2), _w("as", 1.3, 1.4), _w("10", 1.5, 1.7),
        _w("copies", 1.8, 2.1), _w("of", 2.2, 2.3), _w("lull,", 2.4, 2.7),
        _w("the", 2.8, 2.9), _w("next", 3.0, 3.2), _w("as", 3.3, 3.4),
        _w("10", 3.5, 3.7), _w("copies", 3.8, 4.1), _w("of", 4.2, 4.3),
        _w("that", 4.4, 4.6), _w("and", 4.7, 4.8), _w("stack", 4.9, 5.2),
        _w("9", 5.3, 5.4), _w("layers", 5.5, 5.8), _w("deep.", 5.9, 6.2),
    ]
    ranges, _ = detect_retakes(words, min_retake_words=3, min_match_ratio=0.5)
    assert ranges == []


def test_no_pause_retake_still_cut_when_the_take_trails_off():
    """The no-pause gate must not spare a genuine trail-off restart.

    "But this is where it gets… But this is where it gets wild." has no pause and no
    sentence end between the takes (Whisper marks the abort with an ellipsis, which is
    deliberately not a sentence end), but the speaker audibly cut themselves off.
    """
    words = [
        _w("But", 0.0, 0.2), _w("this", 0.3, 0.4), _w("is", 0.5, 0.6),
        _w("where", 0.7, 0.9), _w("it", 1.0, 1.1), _w("gets...", 1.2, 1.5),
        _w("But", 1.6, 1.8), _w("this", 1.9, 2.0), _w("is", 2.1, 2.2),
        _w("where", 2.3, 2.5), _w("it", 2.6, 2.7), _w("gets", 2.8, 3.0),
        _w("wild.", 3.1, 3.5),
    ]
    ranges, _ = detect_retakes(words, min_retake_words=3, min_match_ratio=0.5)
    assert len(ranges) == 1
    assert ranges[0] == pytest.approx((0.0, 1.6))
