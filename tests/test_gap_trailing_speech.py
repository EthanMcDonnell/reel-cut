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


def test_bridges_stop_closure_to_reach_final_syllable():
    # "SSDs" case: WhisperX truncates at 0.40s, but a whole trailing syllable follows
    # past a stop-closure — tail 0.40–0.50, /d/ closure 0.50–0.55 (50 ms), final
    # sibilant 0.55–0.75. The cut must reach ~0.75, not stop at the closure.
    audio = np.concatenate([
        _tone(0.40),            # word body (0–0.40)
        _tone(0.10),            # truncated tail 0.40–0.50
        _tone(0.05, amp=0.0),   # stop closure 0.50–0.55 (< max_closure_ms)
        _tone(0.20),            # final syllable 0.55–0.75
        _tone(0.30, amp=0.0),   # trailing silence
    ])
    speech_end = _find_trailing_speech_end(audio, SR, word_end=0.40, gap_end=1.20, config=CutsConfig())

    assert 0.73 <= speech_end <= 0.77


def test_does_not_bridge_a_long_pause_to_grab_next_word():
    # A pause longer than a stop-closure (150 ms) is a real word boundary — a later
    # burst (breath or next word) must stay in the cut region.
    audio = np.concatenate([
        _tone(0.40),            # word body
        _tone(0.10),            # truncated tail 0.40–0.50
        _tone(0.15, amp=0.0),   # 150 ms pause 0.50–0.65 (> max_closure_ms)
        _tone(0.20),            # later burst 0.65–0.85
        _tone(0.30, amp=0.0),
    ])
    speech_end = _find_trailing_speech_end(audio, SR, word_end=0.40, gap_end=1.20, config=CutsConfig())

    # Stops at the end of the truncated tail (~0.50s); the 0.65–0.85 burst is left out.
    assert 0.48 <= speech_end <= 0.52
