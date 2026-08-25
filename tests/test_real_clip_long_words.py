"""Real-clip regression tests for the over-long-word clamp.

The clamp in _build_gaps runs *before* gaps exist, so neither existing real-clip harness
reaches it: tests/fixtures/retake/<slug>.txt is copied from .debug.4.post-vad, which is
already post-clamp, and test_real_clip_edl.py loads pinned gaps rather than calling
detect_gaps. Both fixture boundaries sit downstream of this code. That is how the
"GitHub" bug shipped — the corrupted 18.366→18.476 span is what a post-vad fixture would
have pinned as correct.

So these tests replay the pre-clamp spans from .debug.3.post-align against the clip's
real 10 ms speech/silence envelope. Assertions are INVARIANTS, for the reason
test_real_clips.py gives: the clamp must land on audible speech, whichever side of the
span WhisperX put it on.
"""
import re
from pathlib import Path

import numpy as np
import pytest

from reelcut.config import load_config
from reelcut.gap_detector import _find_dominant_speech_span

_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "longword"
_REPO_ROOT = Path(__file__).parent.parent
_FIXTURES = sorted(_FIXTURE_DIR.glob("*.txt"))
_SR = 16000
_FRAME = int(0.010 * _SR)


def _load_long_words(path: Path) -> list[tuple[str, float, float, list[bool]]]:
    """Parse a fixture into (word, start, end, per-10ms-frame speech flags)."""
    out = []
    for line in path.read_text().splitlines():
        if line.startswith("#") or not line.strip():
            continue
        word, start, end, envelope = re.split(r"\s{2,}", line.strip(), maxsplit=3)
        flags: list[bool] = []
        for run in envelope.split():
            flags.extend([run[0] == "S"] * int(run[1:]))
        out.append((word, float(start), float(end), flags))
    return out


def _audio_from(start: float, flags: list[bool]) -> np.ndarray:
    """Rebuild a waveform whose frame-by-frame speech verdicts match the envelope."""
    audio = np.zeros(int(start * _SR) + len(flags) * _FRAME + _FRAME, dtype=np.float32)
    t = np.arange(_FRAME) / _SR
    tone = (0.3 * np.sin(2 * np.pi * 200 * t)).astype(np.float32)
    for i, speech in enumerate(flags):
        if speech:
            pos = int(start * _SR) + i * _FRAME
            audio[pos : pos + _FRAME] = tone
    return audio


@pytest.mark.parametrize("fixture", _FIXTURES, ids=lambda p: p.stem)
def test_clamp_lands_on_audible_speech(fixture):
    """Generic invariant: the clamped span must start and end on real speech.

    Under the head-first scan this failed on 'GitHub': the span was clamped to
    18.366-18.476, eleven frames of the *previous* word's decay, leaving the word's
    own 330 ms inside the gap the EDL then cut.
    """
    cuts = load_config(str(_REPO_ROOT / "config.yaml")).cuts
    misses = []
    for word, start, end, flags in _load_long_words(fixture):
        audio = _audio_from(start, flags)
        c_start, c_end = _find_dominant_speech_span(audio, _SR, start, end, cuts)

        span = flags[int((c_start - start) / 0.010) : int((c_end - start) / 0.010)]
        speech_frames = sum(flags)
        if not span or not span[0] or not span[-1]:
            misses.append(f"{word!r} clamped to {c_start:.3f}-{c_end:.3f}s, not bounded by speech")
        elif sum(span) < speech_frames / 2:
            misses.append(
                f"{word!r} clamped to {c_start:.3f}-{c_end:.3f}s, capturing "
                f"{sum(span)} of {speech_frames} speech frames"
            )
    assert not misses, "clamp missed the word's speech:\n  " + "\n  ".join(misses)


def test_hot_take_github_clamps_to_the_late_speech():
    """Regression: "you can buy GitHub stars" rendered as "you can buy stars".

    wav2vec2 stretched 'GitHub' backwards to 18.366-19.932 to butt against 'buy'; the
    word itself is only the 19.606-19.932 run. The clamp must land there, so the cut
    opens at 18.346 (before the word) rather than swallowing it.
    """
    cuts = load_config(str(_REPO_ROOT / "config.yaml")).cuts
    word, start, end, flags = _load_long_words(
        _FIXTURE_DIR / "hot-take-20260825T010121Z.txt"
    )[0]
    assert word == "GitHub"

    c_start, c_end = _find_dominant_speech_span(_audio_from(start, flags), _SR, start, end, cuts)

    assert c_start == pytest.approx(19.606, abs=0.011)
    assert c_end == pytest.approx(19.932, abs=0.011)
