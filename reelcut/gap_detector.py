"""Gap detector — Silero VAD + librosa spectral flatness breath/silence classifier."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import numpy as np

from .config import CutsConfig
from .transcriber import WordTimestamp

GapType = Literal["silence", "breath", "noise", "speech"]


@dataclass
class Gap:
    start: float        # seconds
    end: float          # seconds
    duration_ms: float
    gap_type: GapType
    cut: bool           # True = this gap will be removed


def detect_gaps(
    words: list[WordTimestamp],
    wav_path: str | Path,
    config: CutsConfig,
) -> list[Gap]:
    """Detect and classify inter-word gaps.

    Pipeline:
    1. Enumerate inter-word gaps from WhisperX word timestamps.
    2. Classify each gap using spectral flatness (breath vs silence vs noise).
       VAD is NOT used to filter gaps — on talking-head footage VAD marks everything
       as speech, causing 0 gaps to be detected.
    3. Mark gaps for cutting based on config thresholds.
    """
    wav_path = Path(wav_path)
    audio, sr = _load_audio(wav_path)

    # Compute peak amplitude once for the full track. Used for:
    # - relative breath amplitude ceiling (jumpcutter: breath must be << speech level)
    # - failure tolerance threshold (jumpcutter: allow small fraction of spikes in silence)
    peak_amplitude = float(np.max(np.abs(audio))) if len(audio) > 0 else 1.0

    gaps = _build_gaps(words, audio, sr, config, peak_amplitude)
    return gaps


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_audio(wav_path: Path) -> tuple[np.ndarray, int]:
    import soundfile as sf
    audio, sr = sf.read(str(wav_path), dtype="float32", always_2d=False)
    # soundfile preserves original sr — resample to 16kHz if needed
    if sr != 16000:
        import scipy.signal
        num_samples = int(len(audio) * 16000 / sr)
        audio = scipy.signal.resample(audio, num_samples).astype(np.float32)
        sr = 16000
    return audio, sr


def _classify_gap(
    audio: np.ndarray,
    sr: int,
    start: float,
    end: float,
    duration_ms: float,
    config: CutsConfig,
    peak_amplitude: float,
) -> GapType:
    """Classify a non-speech gap as silence, breath, or noise.

    Two improvements over the original fixed-threshold approach:

    1. Failure tolerance (jumpcutter): if fewer than `failure_tolerance_ratio`
       of samples in the gap exceed the absolute noise floor, the gap is treated
       as silence regardless of its RMS. This prevents a single transient (mouth
       click, mic pop) from raising the RMS and misclassifying an otherwise silent
       gap as noise.

    2. Relative amplitude ceiling for breath (jumpcutter): a gap is only a breath
       if its RMS is below `breath_amplitude_ratio * peak_amplitude`. This ensures
       that only signals well below speech level are classified as breaths — a loud
       burst that happens to be spectrally flat won't be wrongly labelled a breath.
    """
    start_sample = int(start * sr)
    end_sample = int(end * sr)
    chunk = audio[start_sample:end_sample]

    if len(chunk) < 64:
        return "silence"

    abs_chunk = np.abs(chunk)

    # --- Failure tolerance (jumpcutter) ---
    # Convert the absolute dBFS threshold to a linear amplitude value and count
    # how many samples exceed it. If the fraction is below failure_tolerance_ratio,
    # the gap is effectively silent even if the RMS is pulled up by a spike.
    silence_threshold_linear = float(10 ** (config.silence_threshold_db / 20))
    fraction_above = float(np.mean(abs_chunk > silence_threshold_linear))
    if fraction_above < config.failure_tolerance_ratio:
        return "silence"

    # Standard energy check
    rms = float(np.sqrt(np.mean(chunk ** 2)))
    rms_db = 20 * np.log10(rms + 1e-9)

    if rms_db < config.silence_threshold_db:
        return "silence"

    # --- Breath detection ---
    # Requires: spectral flatness (noisy texture) + relative amplitude well below
    # speech level + duration in the breath range (80–700 ms).
    if config.breath_detection and 80 <= duration_ms <= 700:
        flatness = _spectral_flatness(chunk)
        # Relative amplitude check (jumpcutter): breath RMS must be below
        # breath_amplitude_ratio × track peak (default 15%). Loud bursts that
        # are spectrally flat (e.g. wind noise) are excluded.
        is_below_speech_level = rms <= peak_amplitude * config.breath_amplitude_ratio
        if flatness > 0.25 and is_below_speech_level:
            return "breath"

    return "noise"


def _spectral_flatness(chunk: np.ndarray, n_fft: int = 256) -> float:
    """Compute mean spectral flatness (Wiener entropy) without librosa/numba.

    Spectral flatness = geometric_mean(|X|) / arithmetic_mean(|X|).
    Returns a value in [0, 1]; ~1 = noise/breath, ~0 = tonal/speech.
    """
    if len(chunk) < n_fft:
        return 0.0
    # Use scipy STFT for frame-by-frame magnitude spectrum
    import scipy.signal
    _, _, Zxx = scipy.signal.stft(chunk, fs=16000, nperseg=n_fft, noverlap=n_fft // 2)
    mag = np.abs(Zxx) + 1e-10
    # Geometric mean via log trick
    log_geo = np.mean(np.log(mag), axis=0)
    arith = np.mean(mag, axis=0)
    flatness_per_frame = np.exp(log_geo) / (arith + 1e-10)
    return float(np.mean(flatness_per_frame))


def _build_gaps(
    words: list[WordTimestamp],
    audio: np.ndarray,
    sr: int,
    config: CutsConfig,
    peak_amplitude: float,
) -> list[Gap]:
    gaps: list[Gap] = []

    for i in range(len(words) - 1):
        gap_start = words[i].end
        gap_end = words[i + 1].start
        duration_ms = (gap_end - gap_start) * 1000

        if duration_ms <= 0:
            continue

        gap_type = _classify_gap(audio, sr, gap_start, gap_end, duration_ms, config, peak_amplitude)

        # Determine whether to cut based on type and threshold
        if gap_type == "breath":
            should_cut = duration_ms >= config.min_breath_ms
        else:
            should_cut = duration_ms >= config.min_silence_ms

        gaps.append(Gap(
            start=gap_start,
            end=gap_end,
            duration_ms=duration_ms,
            gap_type=gap_type,
            cut=should_cut,
        ))

    return gaps
