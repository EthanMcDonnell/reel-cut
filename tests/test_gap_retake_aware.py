"""Regression test: gap detection must ignore confidence guards for doomed words.

The `hard_floor`/`low_conf` guards in `_build_gaps` exist to avoid clipping *kept*
speech. When a long silence sits in front of a low-confidence word that a later
retake pass deletes, the guard was defending a word that never reaches the output —
stranding the silence as dead air at the retake boundary. Passing the retake ranges
in lets the guard treat doomed words as fully confident, so the silence gets cut.

The pair below proves the fix is scoped: the guard STILL protects a genuinely-kept
low-confidence word (no retake context) and only releases when the word is doomed.
"""
import numpy as np

from reelcut.config import CutsConfig
from reelcut.gap_detector import _build_gaps
from reelcut.transcriber import WordTimestamp

SR = 16000


def _tone(dur_s: float, amp: float = 0.3) -> np.ndarray:
    n = int(dur_s * SR)
    if amp == 0.0:
        return np.zeros(n, dtype=np.float32)
    t = np.arange(n) / SR
    return (amp * np.sin(2 * np.pi * 200 * t)).astype(np.float32)


def _scene():
    """A confident word, 2.5s of silence, then a low-confidence word, then pad.

    The trailing pad keeps the gap clear of the `preserve_end_s` window so only the
    confidence guard is under test. Returns (words, audio, peak_amplitude).
    """
    audio = np.concatenate([
        _tone(0.5),            # "sync."  0.0–0.5  (kept, confident)
        _tone(2.5, amp=0.0),   # silence  0.5–3.0  (the dead air under test)
        _tone(0.2),            # "want"   3.0–3.2  (low confidence)
        _tone(0.6, amp=0.0),   # pad      3.2–3.8  (clip tail, keeps gap off the edge)
    ])
    words = [
        WordTimestamp("sync.", 0.0, 0.5, confidence=0.9),
        WordTimestamp("want", 3.0, 3.2, confidence=0.30),  # < min_word_confidence
    ]
    peak = float(np.max(np.abs(audio)))
    return words, audio, peak


def test_low_conf_word_keeps_its_guard_when_it_survives():
    # No retake context: "want" is real kept speech, so the guard must fire and the
    # 2.5s silence stays (cutting it could clip the onset of an uncertain word).
    words, audio, peak = _scene()
    gaps = _build_gaps(words, audio, SR, CutsConfig(), peak, retake_ranges=None)

    assert len(gaps) == 1
    assert gaps[0].cut is False
    assert "hard_floor" in gaps[0].skip_reason


def test_silence_before_a_doomed_retake_word_is_cut():
    # "want" (3.0–3.2) is inside a retake range that a later pass deletes, so it is not
    # speech to protect — the guard must release and the 2.5s dead air must be cut.
    words, audio, peak = _scene()
    gaps = _build_gaps(words, audio, SR, CutsConfig(), peak, retake_ranges=[(3.0, 4.0)])

    assert len(gaps) == 1
    assert gaps[0].cut is True
    assert gaps[0].skip_reason == ""
