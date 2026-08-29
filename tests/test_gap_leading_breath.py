"""Regression tests for the leading-breath trim (_find_leading_speech_start).

WhisperX back-dates a word's start across the inhale in front of it. The breath then
sits inside the word's own span, where the gap loop (which only measures between words)
never looks and edl.py's fixed pad cannot reach — so the cut ends early and the breath
plays before the sentence starts ("...needs 21 bits." <breath> "The other half...").
"""
import numpy as np

from reelcut.gap_detector import _find_leading_speech_start

SR = 16000


def _seg(dur_s: float, amp: float) -> np.ndarray:
    """A 200 Hz tone at the given amplitude; amp=0 is room silence."""
    n = int(dur_s * SR)
    if amp == 0.0:
        return np.zeros(n, dtype=np.float32)
    t = np.arange(n) / SR
    return (amp * np.sin(2 * np.pi * 200 * t)).astype(np.float32)


# ~-44 dB — an inhale sits above the -45 dB silence floor, which is why the
# speech/silence scans elsewhere cannot see it.
_BREATH = 0.008
_SPEECH = 0.30  # ~-13 dB


def test_breath_before_the_word_advances_the_start():
    # The "The other half" case: 600 ms of inhale inside the word's aligned span.
    audio = np.concatenate([_seg(0.60, _BREATH), _seg(0.40, _SPEECH)])
    onset = _find_leading_speech_start(audio, SR, 0.0, 1.00)

    assert 0.58 <= onset <= 0.62


def test_word_opening_on_speech_is_left_alone():
    audio = _seg(0.50, _SPEECH)
    assert _find_leading_speech_start(audio, SR, 0.0, 0.50) == 0.0


def test_short_soft_onset_is_not_clipped():
    # A quiet fricative onset is far shorter than min_lead_ms — trimming it would
    # eat the head of the word.
    audio = np.concatenate([_seg(0.09, _BREATH), _seg(0.40, _SPEECH)])
    assert _find_leading_speech_start(audio, SR, 0.0, 0.49) == 0.0


def test_loud_onset_is_not_clipped_however_long():
    # A sustained /s/ runs well above the word's peak minus the margin, so length
    # alone must not qualify it as a lead-in.
    audio = np.concatenate([_seg(0.25, _SPEECH / 4), _seg(0.40, _SPEECH)])
    assert _find_leading_speech_start(audio, SR, 0.0, 0.65) == 0.0


def test_scan_stops_at_max_lead():
    # Speech arrives beyond the cap — better to leave the timestamp alone than to
    # advance a start by more than a second on the strength of a level ratio.
    audio = np.concatenate([_seg(1.30, _BREATH), _seg(0.30, _SPEECH)])
    assert _find_leading_speech_start(audio, SR, 0.0, 1.60) == 0.0


def test_never_advances_past_the_word_end():
    # A span that is breath end to end (the word's own peak is the breath) has no
    # step up to find — the scan must stay put rather than run off the span.
    audio = _seg(0.80, _BREATH)
    assert _find_leading_speech_start(audio, SR, 0.0, 0.80) == 0.0
