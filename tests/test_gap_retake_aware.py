"""Regression test: gap detection must ignore confidence guards for doomed words.

The `hard_floor`/`low_conf` guards in `_build_gaps` exist to avoid clipping *kept*
speech. When a long silence sits in front of a low-confidence word that a later
retake pass deletes, the guard was defending a word that never reaches the output —
stranding the silence as dead air at the retake boundary. Passing the retake ranges
in lets the guard treat doomed words as fully confident, so the silence gets cut.

The pair below proves the fix is scoped: a genuinely-kept low-confidence word is STILL
protected from clipping (no retake context) and the silence in front of a doomed word is
still cut. Protection is now a measured speech onset rather than a refusal to cut, so the
first test asserts the invariant — the cut never reaches into the word — not the veto.
"""
import numpy as np
import pytest

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


def test_low_conf_word_is_protected_by_a_measured_onset_not_by_a_veto():
    # No retake context: "want" is real kept speech. It must not be clipped — but the
    # 2.5s of dead air in front of it must still go. The protection comes from measuring
    # the word's true onset in the audio, so assert the invariant (the cut never reaches
    # into the word) rather than the old mechanism (refusing to cut at all).
    cfg = CutsConfig()
    words, audio, peak = _scene()
    gaps = _build_gaps(words, audio, SR, cfg, peak, retake_ranges=None)

    assert len(gaps) == 1
    gap = gaps[0]
    assert gap.cut is True
    # The cut's right edge, exactly as edl.py computes it.
    cut_end = gap.speech_onset - cfg.speech_pad_ms / 1000.0
    assert cut_end <= words[1].start, "cut reached into the low-confidence word"
    assert gap.speech_onset <= words[1].start, "measured onset must never exceed the timestamp"


def test_silence_before_a_doomed_retake_word_is_cut():
    # "want" (3.0–3.2) is inside a retake range that a later pass deletes, so it is not
    # speech to protect — the guard must release and the 2.5s dead air must be cut.
    words, audio, peak = _scene()
    gaps = _build_gaps(words, audio, SR, CutsConfig(), peak, retake_ranges=[(3.0, 4.0)])

    assert len(gaps) == 1
    assert gaps[0].cut is True
    assert gaps[0].skip_reason == ""


def test_measured_onset_pulls_the_cut_back_when_a_word_starts_before_its_timestamp():
    """The protection mechanism itself: WhisperX times "want" 300ms late, so a cut to
    `nxt.start - pad` would eat its opening. The audio scan must find the true onset."""
    cfg = CutsConfig()
    audio = np.concatenate([
        _tone(0.5),            # "sync."   0.0–0.5
        _tone(2.2, amp=0.0),   # silence   0.5–2.7
        _tone(0.5),            # speech    2.7–3.2  ← "want" really starts at 2.7
        _tone(0.6, amp=0.0),   # pad       3.2–3.8
    ])
    words = [
        WordTimestamp("sync.", 0.0, 0.5, confidence=0.9),
        WordTimestamp("want", 3.0, 3.2, confidence=0.30),  # timestamp 300ms late
    ]
    peak = float(np.max(np.abs(audio)))

    gap = _build_gaps(words, audio, SR, cfg, peak, retake_ranges=None)[0]

    assert gap.cut is True
    assert gap.speech_onset == pytest.approx(2.7, abs=0.05), "must find the real onset"
    cut_end = gap.speech_onset - cfg.speech_pad_ms / 1000.0
    assert cut_end < 2.7, "cut must stop before the word's real speech"
