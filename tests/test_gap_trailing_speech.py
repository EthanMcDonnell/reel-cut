"""Regression tests for trailing-consonant tail protection (_find_trailing_speech_end).

WhisperX truncates a word's end timestamp before quiet trailing consonants finish
("MySQL"→/l/, "SSDs"→/z/). The EDL cut starts at the word end, so those tails were
being clipped. The forward scan rescues them by moving the cut to the true speech end.
"""
import numpy as np

from reelcut.config import CutsConfig
from reelcut.gap_detector import _find_trailing_speech_end

SR = 16000


def _tone(dur_s: float, amp: float = 0.3) -> np.ndarray:
    """A tone well above the -40 dB silence floor (speech), or zeros (silence)."""
    n = int(dur_s * SR)
    if amp == 0.0:
        return np.zeros(n, dtype=np.float32)
    t = np.arange(n) / SR
    return (amp * np.sin(2 * np.pi * 200 * t)).astype(np.float32)


def test_truncated_tail_extends_cut_to_true_speech_end():
    # Speech runs 0.0–0.50s but WhisperX declares the word ends at 0.40s (truncated).
    audio = np.concatenate([_tone(0.50), _tone(0.50, amp=0.0)])
    gap_end = 0.90  # next word starts well after the trailing silence

    speech_end = _find_trailing_speech_end(audio, SR, word_end=0.40, gap_end=gap_end, config=CutsConfig())

    # The cut must start at the real speech end (~0.50s), not the truncated 0.40s.
    assert 0.48 <= speech_end <= 0.53


def test_does_not_jump_across_silence_to_grab_later_breath():
    # Word truly ends at 0.40s; a breath burst sits at 0.60–0.70s inside the gap.
    audio = np.concatenate([
        _tone(0.40),            # word
        _tone(0.20, amp=0.0),   # real silence
        _tone(0.10),            # breath / mouth click
        _tone(0.30, amp=0.0),   # trailing silence
    ])
    speech_end = _find_trailing_speech_end(audio, SR, word_end=0.40, gap_end=1.00, config=CutsConfig())

    # Must stop at the first silence (~0.40s) and leave the breath in the cut region.
    assert speech_end <= 0.42
