"""VAD — Silero Voice Activity Detection via ONNX (no PyTorch dependency)."""
from __future__ import annotations

import functools
import urllib.request
from pathlib import Path

import numpy as np

# Pinned to a release tag: the `master` branch currently serves a broken
# re-export of the model that emits near-zero speech probabilities.
_MODEL_URL = (
    "https://raw.githubusercontent.com/snakers4/silero-vad/v5.1.2"
    "/src/silero_vad/data/silero_vad.onnx"
)
_CACHE_PATH = Path.home() / ".cache" / "reelcut" / "silero_vad.onnx"

_SR = 16000
_WINDOW = 512   # samples per inference frame = 32 ms at 16kHz


def get_speech_timestamps(
    audio: np.ndarray,
    sr: int = 16000,
    threshold: float = 0.5,
    min_speech_ms: int = 250,
    min_silence_ms: int = 100,
    speech_pad_ms: int = 30,
) -> list[dict[str, float]]:
    """Return speech segments as list of {"start": seconds, "end": seconds}."""
    if sr != _SR:
        import scipy.signal
        audio = scipy.signal.resample(audio, int(len(audio) * _SR / sr)).astype(np.float32)

    session = _load_session()
    probs = _infer(session, audio)
    return _probs_to_timestamps(
        probs,
        threshold=threshold,
        min_speech_frames=max(1, round(min_speech_ms / 1000 * _SR / _WINDOW)),
        min_silence_frames=max(1, round(min_silence_ms / 1000 * _SR / _WINDOW)),
        pad_frames=max(0, round(speech_pad_ms / 1000 * _SR / _WINDOW)),
        total_frames=len(probs),
    )


# ---------------------------------------------------------------------------
# ONNX model
# ---------------------------------------------------------------------------

@functools.lru_cache(maxsize=1)
def _load_session():
    import onnxruntime as ort

    if not _CACHE_PATH.exists():
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        print(f"[vad] Downloading Silero VAD model → {_CACHE_PATH}", flush=True)
        urllib.request.urlretrieve(_MODEL_URL, _CACHE_PATH)

    return ort.InferenceSession(str(_CACHE_PATH), providers=["CPUExecutionProvider"])


def _infer(session, audio: np.ndarray) -> list[float]:
    """Run frame-by-frame inference. Returns per-frame speech probabilities.

    Supports both Silero VAD v4 (separate h/c states) and v5 (single state tensor).
    The model version is detected from the session's input names.
    """
    pad = (_WINDOW - len(audio) % _WINDOW) % _WINDOW
    if pad:
        audio = np.pad(audio, (0, pad))

    sr = np.array(_SR, dtype=np.int64)
    input_names = {inp.name for inp in session.get_inputs()}
    probs: list[float] = []

    if "state" in input_names:
        # v5: single combined state (2, 1, 128)
        state = np.zeros((2, 1, 128), dtype=np.float32)
        for i in range(0, len(audio), _WINDOW):
            chunk = audio[i : i + _WINDOW].reshape(1, -1).astype(np.float32)
            out, state = session.run(
                ["output", "stateN"],
                {"input": chunk, "sr": sr, "state": state},
            )
            probs.append(float(out[0][0]))
    else:
        # v4: separate h and c states (2, 1, 64)
        h = np.zeros((2, 1, 64), dtype=np.float32)
        c = np.zeros((2, 1, 64), dtype=np.float32)
        for i in range(0, len(audio), _WINDOW):
            chunk = audio[i : i + _WINDOW].reshape(1, -1).astype(np.float32)
            out, h, c = session.run(
                ["output", "hn", "cn"],
                {"input": chunk, "sr": sr, "h": h, "c": c},
            )
            probs.append(float(out[0][0]))

    return probs


# ---------------------------------------------------------------------------
# Probability → timestamps
# ---------------------------------------------------------------------------

def _probs_to_timestamps(
    probs: list[float],
    threshold: float,
    min_speech_frames: int,
    min_silence_frames: int,
    pad_frames: int,
    total_frames: int,
) -> list[dict[str, float]]:
    """State machine: converts per-frame probabilities to speech segments."""
    # Hysteresis: higher threshold to enter speech, slightly lower to leave.
    # Prevents rapid toggling at the boundary.
    enter = threshold
    exit_ = threshold - 0.15

    triggered = False
    speech_start = 0
    silence_count = 0
    segments: list[dict[str, float]] = []

    for i, prob in enumerate(probs):
        if not triggered:
            if prob >= enter:
                triggered = True
                speech_start = i
                silence_count = 0
        else:
            if prob >= exit_:
                silence_count = 0
            else:
                silence_count += 1
                if silence_count >= min_silence_frames:
                    end = i - silence_count + 1
                    if end - speech_start >= min_speech_frames:
                        segments.append(_seg(speech_start, end, pad_frames, total_frames))
                    triggered = False
                    silence_count = 0

    if triggered:
        end = total_frames
        if end - speech_start >= min_speech_frames:
            segments.append(_seg(speech_start, end, pad_frames, total_frames))

    return segments


def _seg(start: int, end: int, pad: int, total: int) -> dict[str, float]:
    return {
        "start": max(0, start - pad) * _WINDOW / _SR,
        "end": min(total, end + pad) * _WINDOW / _SR,
    }
