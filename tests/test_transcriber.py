from dataclasses import dataclass
import pytest
from reelcut.transcriber import _caps_split, _find_sentence_end, _words_to_whisperx_segments


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
