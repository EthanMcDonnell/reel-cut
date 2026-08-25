"""Regression tests for the over-long-word clamp (_find_dominant_speech_span).

WhisperX stretches a word's timestamps across the silence beside it. When it stretches
backwards — pulling the word to butt against the previous word, pause included — the
old head-first scan clamped the word's end to the tail of the *previous* word, dropping
the real audio into the gap where the EDL cut it. Captions kept the word, the audio
lost it ("understand you can buy GitHub stars" played as "...you can buy stars").
"""
import numpy as np

from reelcut.config import CutsConfig
from reelcut.gap_detector import _find_dominant_speech_span

SR = 16000


def _tone(dur_s: float, amp: float = 0.3) -> np.ndarray:
    """A tone well above the -40 dB silence floor (speech), or zeros (silence)."""
    n = int(dur_s * SR)
    if amp == 0.0:
        return np.zeros(n, dtype=np.float32)
    t = np.arange(n) / SR
    return (amp * np.sin(2 * np.pi * 200 * t)).astype(np.float32)


def test_tail_anchored_word_clamps_to_the_late_speech():
    # The "GitHub" case: WhisperX spans 0.0–1.60s, but the word is only the 1.20–1.50
    # run — 0.0–0.12 is the decaying tail of the preceding word.
    audio = np.concatenate([
        _tone(0.12),            # tail of the previous word
        _tone(1.08, amp=0.0),   # the real pause
        _tone(0.30),            # the word itself, 1.20–1.50
        _tone(0.10, amp=0.0),
    ])
    start, end = _find_dominant_speech_span(audio, SR, 0.0, 1.60, CutsConfig())

    assert 1.18 <= start <= 1.23
    assert 1.48 <= end <= 1.53


def test_head_anchored_word_still_clamps_only_the_end():
    # The original case this pre-pass was written for: a short word whose end timestamp
    # was stretched over the following pause. Start must not move.
    audio = np.concatenate([
        _tone(0.25),            # the word, 0.0–0.25
        _tone(1.35, amp=0.0),   # stretched-over silence
    ])
    start, end = _find_dominant_speech_span(audio, SR, 0.0, 1.60, CutsConfig())

    assert start == 0.0
    assert 0.23 <= end <= 0.28


def test_genuinely_long_word_is_left_alone():
    # A held vowel with no sustained internal silence — nothing to clamp.
    audio = _tone(1.60)
    start, end = _find_dominant_speech_span(audio, SR, 0.0, 1.60, CutsConfig())

    assert start == 0.0
    assert end == 1.60
