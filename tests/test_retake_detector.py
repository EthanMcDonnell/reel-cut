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


# ---------------------------------------------------------------------------
# Stumble-retake pass (a flub the speaker self-corrects, then re-records clean)
# ---------------------------------------------------------------------------

def _wc(word: str, start: float, end: float, conf: float) -> WordTimestamp:
    return WordTimestamp(word=word, start=start, end=end, confidence=conf)


# Exact words + confidences from the billion-laughs clip
# (Teleprompter-2026-24-06_00-16-42.debug.4.post-vad, 96.8s–127.2s). The intended line
# "So <entity> means the word lol" is flubbed as "So... No! means the word LOL" (the
# aligner emits 'No!'@0.20, 'So...'@0.40 for the garbled self-correction, and mishears
# the keeper's 'lol' as 'lull'), then re-recorded clean 11s later. The flub shares only
# the run "means the word" with the keeper, so the ratio gate (0.43) and the content
# overlap (0.5) both reject it; only the sub-confidence word + surviving run catch it.
_STUMBLE_RETAKE_REGION = [
    ('shortcuts.', 96.839, 97.320, 0.74),
    ('You', 107.150, 107.251, 0.92), ('define', 107.271, 107.553, 0.75), ('a', 107.574, 107.614, 0.49),
    ('word', 107.634, 107.856, 0.82), ('once,', 107.997, 108.178, 0.81), ('and', 108.461, 108.562, 0.67),
    ('re', 108.663, 108.844, 0.99), ('-use', 108.864, 109.106, 0.96), ('it', 109.167, 109.207, 0.99),
    ('anywhere.', 109.348, 109.570, 0.35), ('So...', 110.130, 110.431, 0.40), ('No!', 110.840, 111.340, 0.20),
    ('means', 111.796, 112.077, 0.79), ('the', 112.118, 112.198, 1.00), ('word', 112.258, 112.499, 0.82),
    ('LOL', 112.579, 112.760, 0.71),
    ('So,', 123.762, 123.903, 0.76), ('ampersand', 124.044, 124.568, 0.73), ('lull', 124.769, 125.111, 0.81),
    ('means', 125.393, 125.654, 0.85), ('the', 125.715, 125.815, 0.85), ('word', 125.856, 126.137, 0.92),
    ('lull.', 126.238, 126.500, 0.85), ('The', 126.921, 127.022, 0.90), ('trick', 127.062, 127.243, 0.90),
]


def test_stumble_retake_cut_by_confidence_and_run():
    """Regression (billion-laughs): a flubbed take "So... No! means the word LOL" that the
    speaker re-records clean must be cut, even though its only shared run is the 3-word
    template and the misheard word drops both the ratio and content-overlap below gate."""
    words = [_wc(t, s, e, c) for t, s, e, c in _STUMBLE_RETAKE_REGION]
    ranges, _ = detect_retakes(
        words, min_retake_words=3, max_retake_gap_s=12.0, min_match_ratio=0.5,
        max_retake_bridge_s=1.0, max_retake_span_s=60.0,
    )
    # The flubbed take (110.130s "So..." → 112.760s "LOL") must be cut whole, ending at
    # the keeper's first word (123.762s) — never reaching into the keeper sentence.
    flub_start, flub_end = 110.130, 112.760
    keeper_start, keeper_end = 123.762, 126.500
    assert any(s <= flub_start and e >= flub_end for s, e in ranges), \
        f"flubbed take not cut; ranges={ranges}"
    swallowed = [(s, e) for s, e in ranges if s < keeper_end and e > keeper_start]
    assert not swallowed, f"keeper sentence swallowed by cut(s): {swallowed}"


def test_low_confidence_word_alone_does_not_trigger_stumble_cut():
    """A take with a sub-confidence word but NO repeated run with a neighbour is not a
    retake — both signals must fire, so the lone low-confidence word is left untouched."""
    words = [
        _wc("Configure", 0.0, 0.4, 0.9), _wc("the", 0.5, 0.7, 0.9), _wc("Kubernetes", 0.8, 1.4, 0.20),
        _wc("cluster.", 1.5, 2.0, 0.9),
        _wc("Then", 3.0, 3.3, 0.9), _wc("restart", 3.4, 3.9, 0.9), _wc("every", 4.0, 4.3, 0.9),
        _wc("node.", 4.4, 4.9, 0.9),
    ]
    ranges, _ = detect_retakes(
        words, min_retake_words=3, max_retake_gap_s=12.0, min_match_ratio=0.5,
    )
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
