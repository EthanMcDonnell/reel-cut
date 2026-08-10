from dataclasses import dataclass, field
import pytest
from reelcut.transcriber import (
    _caps_split,
    _enforce_monotonic_timestamps,
    _Expansion,
    _expand_to_sentence,
    _find_sentence_end,
    _merge_leading_comma_tokens,
    _merge_retranscribe_windows,
    _reconcile_retranscribed,
    _words_to_whisperx_segments,
    is_sentence_boundary,
    WordTimestamp,
)


@dataclass
class W:
    word: str
    start: float
    end: float


# ---------------------------------------------------------------------------
# _caps_split
# ---------------------------------------------------------------------------

def test_caps_split_below_floor():
    assert not _caps_split("Capital", 5.0, caps_floor_s=10.0, hard_cap_s=20.0)

def test_caps_split_at_caps_floor():
    assert _caps_split("Capital", 10.0, caps_floor_s=10.0, hard_cap_s=20.0)

def test_caps_split_hard_cap_fires_without_caps():
    assert _caps_split("lowercase", 20.0, caps_floor_s=10.0, hard_cap_s=20.0)

def test_caps_split_lowercase_below_hard_cap():
    assert not _caps_split("lowercase", 15.0, caps_floor_s=10.0, hard_cap_s=20.0)


# ---------------------------------------------------------------------------
# _find_sentence_end
# ---------------------------------------------------------------------------

FABLE_WORDS = [
    W("Everything", 5.94, 6.56),
    W("you",        6.56, 6.78),
    W("need",       6.78, 6.94),
    W("to",         6.94, 7.04),
    W("know",       7.04, 7.18),
    W("about",      7.18, 7.44),
    W("Fable's",    7.44, 7.84),
    W("leaked",     7.84, 8.06),
    W("system",     8.06, 8.38),
    W("prompt",     8.38, 8.66),
    W("before",     8.66, 8.98),
    W("Anthropic",  8.98, 9.48),
    W("takes",      9.48, 9.82),
    W("it",         9.82, 9.96),
    W("down.",      9.96, 10.24),
]


def test_proper_noun_mid_sentence_does_not_split_expand():
    """Caps fallback at max_duration_s=20s should not stop at 'Fable's' (~1.5s in)."""
    end_idx = _find_sentence_end(FABLE_WORDS, 0, 0, caps_floor_s=20.0, hard_cap_s=20.0)
    assert FABLE_WORDS[end_idx].word == "down."


def test_proper_noun_mid_sentence_does_not_split_segments():
    """Caps fallback at 10s should not stop at 'Fable's' (~1.5s in)."""
    end_idx = _find_sentence_end(FABLE_WORDS, 0, 0, caps_floor_s=10.0, hard_cap_s=20.0)
    assert FABLE_WORDS[end_idx].word == "down."


def test_caps_split_fires_after_floor():
    """A capitalised word at 12s elapsed should split at caps_floor_s=10."""
    words = [W(f"word{i}", float(i), float(i) + 0.9) for i in range(12)]
    words += [W("Capital", 12.0, 12.5), W("end.", 12.5, 13.0)]
    end_idx = _find_sentence_end(words, 0, 0, caps_floor_s=10.0, hard_cap_s=20.0)
    assert words[end_idx].word == "word11"


def test_caps_split_does_not_fire_before_hard_cap():
    """Same words — caps at 20s floor means scan reaches 'end.' instead."""
    words = [W(f"word{i}", float(i), float(i) + 0.9) for i in range(12)]
    words += [W("Capital", 12.0, 12.5), W("end.", 12.5, 13.0)]
    end_idx = _find_sentence_end(words, 0, 0, caps_floor_s=20.0, hard_cap_s=20.0)
    assert words[end_idx].word == "end."


def test_empty_words():
    assert _find_sentence_end([], 0, 0, caps_floor_s=10.0, hard_cap_s=20.0) == len([]) - 1


# ---------------------------------------------------------------------------
# is_sentence_boundary
# ---------------------------------------------------------------------------

def test_boundary_terminal_punctuation():
    assert is_sentence_boundary("down.", "Next", gap_s=0.0)
    assert is_sentence_boundary("really?", "next", gap_s=0.0)
    assert is_sentence_boundary("wow!", "then", gap_s=0.0)

def test_boundary_no_punctuation_no_caps():
    assert not is_sentence_boundary("the", "cookie", gap_s=1.0)

def test_boundary_caps_after_pause_recovers_missing_fullstop():
    """Whisper dropped the full stop, but a real pause precedes a capitalised word."""
    assert is_sentence_boundary("down", "Anthropic", gap_s=0.5)

def test_boundary_caps_without_pause_is_not_a_boundary():
    """Mid-sentence proper noun (no preceding pause) must not split."""
    assert not is_sentence_boundary("about", "Fable's", gap_s=0.1)

def test_boundary_none_next_word():
    assert not is_sentence_boundary("end", None, gap_s=5.0)

def test_boundary_clause_punct_only_when_enabled():
    """Commas/semicolons/colons are cut-permission boundaries (EDL), not caption splits."""
    assert not is_sentence_boundary("words,", "and", gap_s=0.0)
    assert is_sentence_boundary("words,", "and", gap_s=0.0, include_clause=True)
    assert is_sentence_boundary("list:", "one", gap_s=0.0, include_clause=True)


# ---------------------------------------------------------------------------
# _expand_to_sentence
# ---------------------------------------------------------------------------

def test_expand_low_conf_window_reaches_previous_sentence_start():
    """Regression: 'fresh [out of the oven] See,' — the dropped phrase lives in the
    0.7s gap before the low-conf 'See,'. Case 4 anchors the window on the previous
    word's *start* (fresh, 27.44); expansion must carry the edge back to the previous
    sentence's onset ('Something') — a clean, silence-preceded boundary — rather than
    cutting mid-word at the imprecise fresh.end timestamp."""
    words = [
        W("Something", 27.00, 27.44),  # previous sentence start (capitalised)
        W("fresh",     27.44, 27.90),
        W("See,",      28.60, 29.16),  # capitalised — Whisper's spurious boundary
        W("a",         29.16, 29.30),
        W("cookie.",   29.30, 29.80),
    ]
    exp_start, exp_end, _ = _expand_to_sentence(words, win_start=27.44, win_end=29.16)
    assert exp_start == pytest.approx(27.00)  # back to the sentence onset, not mid-word
    assert exp_end >= 29.16


def test_expand_does_not_shrink_below_window_start():
    """Clamp invariant: expansion must never move the start later than win_start,
    even when the backward scan stops on a capitalised word after it."""
    words = [
        W("fresh",  27.44, 27.90),
        W("See,",   28.60, 29.16),   # capitalised — would otherwise anchor exp_start here
        W("a",      29.16, 29.30),
        W("cookie.", 29.30, 29.80),
    ]
    exp_start, _, _ = _expand_to_sentence(words, win_start=27.90, win_end=29.16)
    assert exp_start <= 27.90  # not shrunk forward to 28.60


def test_expand_end_never_shrinks_below_window():
    """exp_end must never fall below the requested win_end."""
    words = [W("a", 0.0, 0.5), W("Word.", 0.5, 1.0), W("next", 2.0, 2.5)]
    _, exp_end, _ = _expand_to_sentence(words, win_start=0.0, win_end=1.8)
    assert exp_end >= 1.8


def test_expand_still_grows_to_sentence_bounds():
    """Normal case: window over an interior word expands out to sentence start/end."""
    words = [
        W("The",     0.0, 0.3),
        W("quick",   0.3, 0.6),
        W("brown",   0.6, 0.9),
        W("fox.",    0.9, 1.2),
    ]
    exp_start, exp_end, _ = _expand_to_sentence(words, win_start=0.6, win_end=0.9)
    assert exp_start == pytest.approx(0.0)   # back to "The"
    assert exp_end == pytest.approx(1.2)     # forward to "fox."


def test_expand_hard_cap_snaps_back_to_a_word_boundary():
    """Regression: the 20s cap severed 'or' (37.680-39.260) mid-word, so the word was
    replaced out of the transcript while Whisper only saw its opening 260ms — the word
    vanished. The capped end must land on a word boundary, never inside a word."""
    words = [
        W("I", 0.0, 0.5),
        W("know", 0.5, 36.460),   # long filler run standing in for the real sentence
        W("guess", 36.460, 37.680),   # the last word ending inside the cap
        W("or", 37.680, 39.260),  # straddles the 20.0s cap at 20.0
    ]
    exp_start, exp_end, hard_capped = _expand_to_sentence(
        words, win_start=0.0, win_end=39.260, max_duration_s=20.0,
    )
    assert hard_capped
    # No word may straddle the returned end.
    assert not any(w.start < exp_end < w.end for w in words)


def test_expand_uncapped_window_is_not_snapped():
    """The snap-back only applies when the cap binds; normal windows keep their end."""
    words = [W("The", 0.0, 0.3), W("quick", 0.3, 0.6), W("fox.", 0.6, 1.2)]
    _, exp_end, hard_capped = _expand_to_sentence(words, win_start=0.0, win_end=0.6)
    assert not hard_capped
    assert exp_end == pytest.approx(1.2)


# ---------------------------------------------------------------------------
# _words_to_whisperx_segments
# ---------------------------------------------------------------------------

def test_segments_single_sentence():
    segs = _words_to_whisperx_segments(FABLE_WORDS)
    assert len(segs) == 1
    assert segs[0]["text"].startswith("Everything")
    assert segs[0]["text"].endswith("down.")


def test_segments_splits_at_punctuation():
    words = [
        W("First",   0.0, 0.5),
        W("sentence.", 0.5, 1.0),
        W("Second",  1.0, 1.5),
        W("one",     1.5, 2.0),
        W("here.",   2.0, 2.5),
    ]
    segs = _words_to_whisperx_segments(words)
    assert len(segs) == 1  # first sentence only 2 words, merges with second


def test_segments_short_sentence_merges():
    """A 2-word sentence before a 3-word sentence should be merged (MIN_WORDS=3)."""
    words = [
        W("Hi.",   0.0, 0.3),
        W("How",   0.3, 0.6),
        W("are",   0.6, 0.9),
        W("you?",  0.9, 1.2),
    ]
    segs = _words_to_whisperx_segments(words)
    assert len(segs) == 1
    assert "Hi." in segs[0]["text"]
    assert "you?" in segs[0]["text"]


def test_segments_caps_split_long_chunk():
    """12 words over 12s then a capitalised word should produce 2 segments."""
    words = [W(f"word{i}", float(i), float(i) + 0.9) for i in range(12)]
    words += [W("Capital", 12.0, 12.5), W("sentence.", 12.5, 13.0)]
    segs = _words_to_whisperx_segments(words)
    assert len(segs) == 2
    assert segs[1]["text"].startswith("Capital")


def test_segments_empty():
    assert _words_to_whisperx_segments([]) == []


# ---------------------------------------------------------------------------
# _reconcile_retranscribed
# ---------------------------------------------------------------------------

def _wt(word, start, end, confidence):
    return WordTimestamp(word=word, start=start, end=end, confidence=confidence)


def test_reconcile_rescues_casing_mismatch():
    """Retrans 'Leaked'@0.28 should be rescued because original 'leaked'@0.58 is confident."""
    original = [_wt("leaked", 7.84, 8.06, 0.58)]
    retrans  = [_wt("Leaked", 0.0,  0.22, 0.28)]  # clip-relative, offset already applied → abs 7.84
    # Apply offset manually as the main loop does before calling _reconcile_retranscribed
    for w in retrans:
        w.start += 7.84
        w.end = min(w.end + 7.84, 10.24)

    kept, rescued = _reconcile_retranscribed(retrans, original, win_end=10.24, conf_threshold=0.5)

    assert len(kept) == 1
    assert kept[0].word == "leaked"       # original's lowercase casing
    assert kept[0].confidence == 0.58     # original's confidence
    assert kept[0].start == pytest.approx(7.84)  # retrans timestamp preserved
    assert len(rescued) == 1


def test_reconcile_no_rescue_when_original_below_rescue_floor():
    """Word is dropped when the original is also below rescue_floor."""
    original = [_wt("leaked", 7.84, 8.06, 0.03)]
    retrans  = [_wt("Leaked", 7.84, 8.06, 0.04)]

    kept, rescued = _reconcile_retranscribed(
        retrans, original, win_end=10.24, conf_threshold=0.5, rescue_floor=0.05
    )

    assert kept == []
    assert rescued == []


def test_reconcile_rescue_when_original_meets_rescue_floor():
    """Word is rescued when retrans is below conf_threshold but original meets rescue_floor."""
    original = [_wt("leaked", 7.84, 8.06, 0.30)]
    retrans  = [_wt("Leaked", 7.84, 8.06, 0.08)]

    kept, rescued = _reconcile_retranscribed(
        retrans, original, win_end=10.24, conf_threshold=0.5, rescue_floor=0.05
    )

    assert len(kept) == 1
    assert kept[0].word == "leaked"
    assert kept[0].confidence == 0.30
    assert len(rescued) == 1


def test_reconcile_no_rescue_for_new_word_not_in_original():
    """A genuine false-start word not in the original is dropped normally."""
    original = [_wt("system", 8.06, 8.38, 0.72)]
    retrans  = [_wt("actually", 8.06, 8.38, 0.28)]

    kept, rescued = _reconcile_retranscribed(retrans, original, win_end=10.24, conf_threshold=0.5)

    assert kept == []
    assert rescued == []


def test_reconcile_drops_out_of_bounds():
    """A word at or past win_end is dropped regardless of confidence or match."""
    original = [_wt("leaked", 7.84, 8.06, 0.80)]
    retrans  = [_wt("leaked", 10.24, 10.50, 0.90)]  # starts at win_end — out of bounds

    kept, rescued = _reconcile_retranscribed(retrans, original, win_end=10.24, conf_threshold=0.5)

    assert kept == []
    assert rescued == []


def test_reconcile_passes_confident_words_unchanged():
    """Words already at/above conf_threshold pass through untouched."""
    original = []
    retrans  = [_wt("system", 8.06, 8.38, 0.72)]

    kept, rescued = _reconcile_retranscribed(retrans, original, win_end=10.24, conf_threshold=0.5)

    assert len(kept) == 1
    assert kept[0].word == "system"
    assert kept[0].confidence == 0.72
    assert rescued == []


def test_reconcile_reverts_confidence_regression():
    """Regression: short sub-clips turned confident words into different, weaker ones —
    'Like'@0.78 → 'Lie.'@0.20 and 'API?'@0.86 → 'IPL.'@0.64 both shipped in the transcript.
    Same word count means position i is comparable, so both revert to the original."""
    original = [_wt("Like", 12.30, 12.64, 0.78), _wt("API?", 16.30, 16.72, 0.86)]
    retrans  = [_wt("Lie.", 12.30, 12.64, 0.20), _wt("IPL.", 16.30, 16.72, 0.64)]

    kept, rescued = _reconcile_retranscribed(
        retrans, original, win_end=17.0, conf_threshold=0.10, regression_margin=0.20
    )

    assert [w.word for w in kept] == ["Like", "API?"]
    assert [w.confidence for w in kept] == [0.78, 0.86]
    assert kept[0].start == pytest.approx(12.30)   # retrans timestamps preserved
    assert len(rescued) == 2


def test_reconcile_keeps_retranscription_improvements():
    """The guard is one-directional: a retranscribed word more confident than the
    original is exactly what retranscription is for and must survive untouched."""
    original = [_wt("but", 24.09, 24.19, 0.21)]
    retrans  = [_wt("but", 24.09, 24.19, 0.90)]

    kept, _ = _reconcile_retranscribed(
        retrans, original, win_end=25.0, conf_threshold=0.10, regression_margin=0.20
    )

    assert kept[0].confidence == 0.90


def test_reconcile_regression_guard_needs_matching_word_counts():
    """Positional comparison is only sound when both passes returned the same number of
    words; a differing count (a recovered false start) leaves the guard disarmed."""
    original = [_wt("guess", 37.12, 37.68, 0.89)]
    retrans  = [_wt("I", 37.12, 37.30, 0.40), _wt("Guest.", 37.30, 37.68, 0.33)]

    kept, _ = _reconcile_retranscribed(
        retrans, original, win_end=38.0, conf_threshold=0.10, regression_margin=0.20
    )

    assert [w.word for w in kept] == ["I", "Guest."]


# ---------------------------------------------------------------------------
# _merge_retranscribe_windows
# ---------------------------------------------------------------------------

def test_merge_gap_within_tolerance_collapses_to_one_window():
    """Gap of 0.5s between windows merges when merge_gap_s=1.0 (the real-world retake case)."""
    windows = [(70.760, 77.720, "wide+low_conf_word"), (78.220, 88.580, "low_conf_word")]
    result = _merge_retranscribe_windows(windows, merge_gap_s=1.0)
    assert len(result) == 1
    assert result[0] == (70.760, 88.580, "wide+low_conf_word")


def test_merge_gap_exceeds_tolerance_stays_separate():
    """Gap of 0.5s between windows does NOT merge when merge_gap_s=0.0 (old behaviour)."""
    windows = [(70.760, 77.720, "wide+low_conf_word"), (78.220, 88.580, "low_conf_word")]
    result = _merge_retranscribe_windows(windows, merge_gap_s=0.0)
    assert len(result) == 2


def test_merge_overlapping_windows_still_merge():
    """Overlapping windows always merge regardless of merge_gap_s."""
    windows = [(10.0, 20.0, "low_conf_word"), (15.0, 25.0, "wide")]
    result = _merge_retranscribe_windows(windows, merge_gap_s=0.0)
    assert len(result) == 1
    assert result[0][0] == 10.0
    assert result[0][1] == 25.0


def test_merge_gap_exactly_at_tolerance_merges():
    """A gap exactly equal to merge_gap_s is included (≤, not <)."""
    windows = [(0.0, 10.0, "a"), (11.0, 20.0, "b")]
    result = _merge_retranscribe_windows(windows, merge_gap_s=1.0)
    assert len(result) == 1


def test_merge_gap_just_beyond_tolerance_stays_separate():
    """A gap of 1.001s does not merge when merge_gap_s=1.0."""
    windows = [(0.0, 10.0, "a"), (11.001, 20.0, "b")]
    result = _merge_retranscribe_windows(windows, merge_gap_s=1.0)
    assert len(result) == 2


def test_merge_duplicate_label_not_doubled():
    """Merging two windows with the same label keeps the label once."""
    windows = [(0.0, 5.0, "low_conf_word"), (5.5, 10.0, "low_conf_word")]
    result = _merge_retranscribe_windows(windows, merge_gap_s=1.0)
    assert len(result) == 1
    assert result[0][2] == "low_conf_word"


# ---------------------------------------------------------------------------
# _merge_leading_comma_tokens
# ---------------------------------------------------------------------------

def _w(word: str, start: float, end: float, conf: float = 0.9) -> WordTimestamp:
    return WordTimestamp(word=word, start=start, end=end, confidence=conf, clip_path="x.wav")


def test_comma_token_merges_into_previous_word():
    """["30", ",000"] collapses to a single "30,000" word."""
    words = [_w("thirty", 0.0, 0.4), _w("30", 0.4, 0.7), _w(",000", 0.7, 1.0)]
    result = _merge_leading_comma_tokens(words)
    assert len(result) == 2
    assert result[1].word == "30,000"
    assert result[1].start == 0.4
    assert result[1].end == 1.0


def test_normal_words_pass_through_unchanged():
    """Words without a leading comma are left alone."""
    words = [_w("over", 0.0, 0.3), _w("thirty", 0.3, 0.6), _w("thousand", 0.6, 1.0)]
    result = _merge_leading_comma_tokens(words)
    assert [w.word for w in result] == ["over", "thirty", "thousand"]


# ---------------------------------------------------------------------------
# _enforce_monotonic_timestamps
# ---------------------------------------------------------------------------

def _exp(word: str, start: float, end: float, conf: float = 0.9) -> _Expansion:
    """Pair a collapsed word's pre-align original with a token list (unused by the guard)."""
    return _Expansion(orig_word=_w(word, start, end, conf), tokens=[word])


def test_monotonic_guard_repairs_hook4_alignment_corruption():
    """Regression: WhisperX scrambled the tail of 'save $75 million in the process.'

    Pre-align (Whisper) timestamps were clean and monotonic; alignment collapsed
    'million'/'in'/'process' backward (overlapping '$75') and stranded 'the',
    which drove a spurious mid-phrase cut. The guard must restore the run to its
    monotonic pre-align timestamps.
    """
    # expansion.orig_word carries the clean pre-align timestamps.
    expansion = [
        _exp("$75", 28.630, 29.250, 0.77),
        _exp("million", 29.250, 29.710, 0.63),
        _exp("in", 29.710, 30.210, 0.87),
        _exp("the", 30.210, 30.330, 0.81),
        _exp("process.", 30.330, 30.630, 0.88),
    ]
    # Corrupted post-collapse alignment output (1:1 with expansion).
    collapsed = [
        _w("$75", 28.630, 29.250, 0.77),
        _w("million", 28.641, 28.862, 0.24),
        _w("in", 28.882, 28.922, 0.50),
        _w("the", 30.210, 30.330, 0.81),
        _w("process.", 29.023, 29.264, 0.31),
    ]

    result = _enforce_monotonic_timestamps(collapsed, expansion)

    # Word order and text are preserved; timestamps are now monotonic.
    assert [w.word for w in result] == ["$75", "million", "in", "the", "process."]
    starts = [w.start for w in result]
    ends = [w.end for w in result]
    assert starts == sorted(starts)
    assert all(ends[i] <= starts[i + 1] for i in range(len(result) - 1))
    # The three corrupted words fell back to their pre-align timestamps.
    assert (result[1].start, result[1].end) == (29.250, 29.710)   # million
    assert (result[2].start, result[2].end) == (29.710, 30.210)   # in
    assert (result[4].start, result[4].end) == (30.330, 30.630)   # process.


def test_monotonic_guard_leaves_clean_alignment_untouched():
    """A well-ordered alignment must pass through byte-for-byte (no over-firing)."""
    expansion = [
        _exp("save", 0.0, 0.4, 0.5),   # pre-align differs from aligned below
        _exp("the", 0.4, 0.6, 0.5),
        _exp("cloud", 0.6, 1.0, 0.5),
    ]
    collapsed = [
        _w("save", 0.05, 0.42, 0.9),
        _w("the", 0.45, 0.61, 0.9),
        _w("cloud", 0.63, 0.98, 0.9),
    ]
    result = _enforce_monotonic_timestamps(collapsed, expansion)
    # Aligned timestamps kept, not the pre-align originals.
    assert [(w.start, w.end, w.confidence) for w in result] == [
        (0.05, 0.42, 0.9), (0.45, 0.61, 0.9), (0.63, 0.98, 0.9),
    ]


def test_monotonic_guard_restores_single_overlapping_word():
    """A lone backward word is restored; its neighbours are left alone."""
    expansion = [
        _exp("a", 1.0, 1.2),
        _exp("b", 1.2, 1.4),   # clean pre-align
        _exp("c", 1.4, 1.6),
    ]
    collapsed = [
        _w("a", 1.0, 1.2),
        _w("b", 0.5, 0.7),     # aligned before 'a' → must be restored
        _w("c", 1.4, 1.6),
    ]
    result = _enforce_monotonic_timestamps(collapsed, expansion)
    assert (result[1].start, result[1].end) == (1.2, 1.4)
    assert (result[0].start, result[2].start) == (1.0, 1.4)


def test_monotonic_guard_restores_predecessor_aligned_too_late():
    """Regression: 'I know, it's not great...' came out as 'know, I it's not great'.

    Alignment pushed 'I' *later* than 'know'. Falling back only the later word
    ('know', to its correct 18.510-18.790) still leaves it behind 'I' at the
    corrupted 18.692, so the pair stays inverted. The predecessor must fall back
    too.
    """
    expansion = [
        _exp("I", 18.430, 18.510, 0.95),
        _exp("know,", 18.510, 18.790, 0.82),
        _exp("it's", 18.990, 19.230, 0.94),
    ]
    collapsed = [
        _w("I", 18.692, 18.793, 0.75),      # aligned too late — the real culprit
        _w("know,", 18.510, 18.790, 0.82),
        _w("it's", 19.095, 19.216, 0.85),
    ]

    result = _enforce_monotonic_timestamps(collapsed, expansion)

    assert [w.word for w in result] == ["I", "know,", "it's"]
    starts = [w.start for w in result]
    assert starts == sorted(starts)
    assert (result[0].start, result[0].end) == (18.430, 18.510)   # predecessor restored
