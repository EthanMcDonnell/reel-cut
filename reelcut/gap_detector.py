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
    start: float           # seconds, = words[i].end (used for map lookup in edl.py)
    end: float             # seconds, = words[i+1].start
    effective_start: float # true silence onset — may be earlier than start when Whisper
                           # extends a word's end timestamp into trailing silence
    speech_end: float      # true end of the preceding word's speech, >= start — later
                           # than start when Whisper truncates a quiet trailing consonant
                           # (sibilant/liquid). edl.py cuts here so tails aren't clipped.
    duration_ms: float
    gap_type: GapType
    cut: bool              # True = this gap will be removed
    skip_reason: str = ""  # non-empty when cut=False; human-readable explanation


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


def _find_silence_onset(
    audio: np.ndarray,
    sr: int,
    before_t: float,
    scan_s: float,
    config: CutsConfig,
) -> float:
    """Scan backward from before_t to find where audio actually goes silent.

    Whisper commonly extends a word's end timestamp into the trailing silence
    (the gap gets attributed to the previous word). This finds the true onset of
    silence so the cut starts where energy actually drops, not at the timestamp.

    Returns a time <= before_t. Falls back to before_t if no silence found.
    """
    frame_size = max(64, int(0.010 * sr))  # 10 ms frames
    end_sample = int(before_t * sr)
    start_sample = max(0, end_sample - int(scan_s * sr))
    silence_thresh = float(10 ** (config.silence_threshold_db / 20))

    pos = end_sample
    while pos - frame_size >= start_sample:
        frame = audio[pos - frame_size : pos]
        if float(np.mean(np.abs(frame) > silence_thresh)) < config.failure_tolerance_ratio:
            return pos / sr  # this frame is silent — speech ended here
        pos -= frame_size

    return before_t


def _find_speech_end_forward(
    audio: np.ndarray,
    sr: int,
    word_start: float,
    word_end: float,
    config: CutsConfig,
    min_silence_ms: float = 100.0,
) -> float:
    """Scan forward from word_start to find the first sustained silence within the word span.

    WhisperX sometimes stretches a word's end timestamp to cover the entire following
    silence (especially for short function words like "The", "But"). This makes the
    inter-word gap trivially small and invisible to the gap detector. This function
    finds the true end of speech so the word can be clamped before gap detection.

    Returns a time in [word_start, word_end]. Returns word_end unchanged if no
    sustained silence is found (the word is genuinely long, e.g. a held vowel).
    """
    frame_size = max(64, int(0.010 * sr))  # 10ms frames
    required_frames = max(1, int(min_silence_ms / 10))
    silence_thresh = float(10 ** (config.silence_threshold_db / 20))

    start_sample = int(word_start * sr)
    end_sample = int(word_end * sr)

    consecutive_silent = 0
    first_silent_pos: int | None = None

    for pos in range(start_sample, end_sample, frame_size):
        frame = audio[pos : pos + frame_size]
        if len(frame) < 64:
            break
        fraction_above = float(np.mean(np.abs(frame) > silence_thresh))
        if fraction_above < config.failure_tolerance_ratio:
            if consecutive_silent == 0:
                first_silent_pos = pos
            consecutive_silent += 1
            if consecutive_silent >= required_frames:
                return first_silent_pos / sr  # type: ignore[operator]
        else:
            consecutive_silent = 0
            first_silent_pos = None

    return word_end


def _find_trailing_speech_end(
    audio: np.ndarray,
    sr: int,
    word_end: float,
    gap_end: float,
    config: CutsConfig,
    max_extend_ms: float = 400.0,
) -> float:
    """Scan forward from word_end to find where the word's trailing speech ends.

    WhisperX often truncates a word's end timestamp before quiet trailing consonants
    finish (sibilants/liquids: "MySQL"→/l/, "SSDs"→/z/). Because edl.py starts its cut
    at the word end, those tails get clipped. This walks forward and stops at the first
    silent frame, so the cut can start after the real speech end.

    A truncated consonant is *contiguous* with the word, so the first silence marks its
    end — stopping there avoids jumping across the gap to grab a later breath or click.
    Returns a time in [word_end, min(gap_end, word_end + max_extend)]. Returns word_end
    unchanged when audio is already silent there (accurate alignment — the common case).
    """
    frame_size = max(64, int(0.010 * sr))  # 10 ms frames
    silence_thresh = float(10 ** (config.silence_threshold_db / 20))

    start_sample = int(word_end * sr)
    limit = min(gap_end, word_end + max_extend_ms / 1000.0)
    end_sample = int(limit * sr)

    for pos in range(start_sample, end_sample, frame_size):
        frame = audio[pos : pos + frame_size]
        if len(frame) < 64:
            break
        if float(np.mean(np.abs(frame) > silence_thresh)) < config.failure_tolerance_ratio:
            return pos / sr  # first silent frame — speech ended here

    # No silence inside the window — keep the whole tail up to the limit.
    return limit


_LONG_WORD_DUR_S = 1.5  # words longer than this are suspect for alignment errors


def _build_gaps(
    words: list[WordTimestamp],
    audio: np.ndarray,
    sr: int,
    config: CutsConfig,
    peak_amplitude: float,
) -> list[Gap]:
    gaps: list[Gap] = []

    # Pre-pass: clamp words whose WhisperX-assigned duration is suspiciously long.
    # WhisperX sometimes stretches a short word's end timestamp across the entire
    # silence that follows it. The inter-word gap is then only a few ms and is never
    # cut. Scanning forward finds the true speech end and restores a real gap.
    for word in words[:-1]:
        if word.end - word.start > _LONG_WORD_DUR_S:
            true_end = _find_speech_end_forward(audio, sr, word.start, word.end, config)
            if true_end < word.end - 0.050:  # at least 50ms of silence found
                word.end = true_end

    for i in range(len(words) - 1):
        raw_start = words[i].end
        gap_end = words[i + 1].start

        # For normal words use a tight scan window (word_end_scan_ms) — wide
        # windows cause _find_silence_onset to land inside stop-consonant closures
        # ("t","p","k") which briefly look like silence and clip the word end.
        # Only widen when Whisper has over-extended the end timestamp past the
        # next word's start (impossible gap); the long-word pre-pass above already
        # handles the stretched-timestamp case before we reach here.
        word_duration = words[i].end - words[i].start
        if raw_start > gap_end or word_duration > 1.5:
            scan_s = max(0.20, raw_start - words[i].start)
        else:
            scan_s = config.word_end_scan_ms / 1000.0
        effective_start = _find_silence_onset(audio, sr, raw_start, scan_s=scan_s, config=config)

        # Forward-only tail protection: if speech continues past the WhisperX word
        # end, move the cut boundary to the true speech end so the trailing consonant
        # isn't clipped. Never earlier than raw_start, so it can't land inside the word.
        speech_end = _find_trailing_speech_end(audio, sr, raw_start, gap_end, config)

        duration_ms = (gap_end - effective_start) * 1000

        if duration_ms <= 0:
            continue

        gap_type = _classify_gap(audio, sr, effective_start, gap_end, duration_ms, config, peak_amplitude)

        prev_conf = words[i].confidence
        next_conf = words[i + 1].confidence

        clip_duration_s = len(audio) / sr
        skip_reason = ""
        if config.preserve_start_s > 0 and effective_start < config.preserve_start_s:
            should_cut = False
            skip_reason = f"preserve_start ({effective_start:.3f}s < {config.preserve_start_s}s)"
        elif config.preserve_end_s > 0 and gap_end > clip_duration_s - config.preserve_end_s:
            should_cut = False
            skip_reason = f"preserve_end ({gap_end:.3f}s > clip-{config.preserve_end_s}s)"
        elif next_conf < config.min_word_confidence:
            # The word we're cutting INTO is uncertain — don't cut regardless of prev side.
            should_cut = False
            skip_reason = f"hard_floor (next_conf={next_conf:.2f} < {config.min_word_confidence})"
        elif prev_conf < config.min_word_confidence:
            # Only the preceding word is uncertain — apply relaxed threshold rather than blocking.
            should_cut = duration_ms >= config.low_confidence_min_gap_ms
            if not should_cut:
                skip_reason = f"low_conf ({duration_ms:.0f}ms < {config.low_confidence_min_gap_ms}ms, conf={prev_conf:.2f})"
        elif min(prev_conf, next_conf) < config.low_confidence_threshold:
            should_cut = duration_ms >= config.low_confidence_min_gap_ms
            if not should_cut:
                skip_reason = f"low_conf ({duration_ms:.0f}ms < {config.low_confidence_min_gap_ms}ms, conf={min(prev_conf, next_conf):.2f})"
        elif gap_type == "breath":
            should_cut = duration_ms >= config.min_breath_ms
            if not should_cut:
                skip_reason = f"breath too short ({duration_ms:.0f}ms < {config.min_breath_ms}ms)"
        else:
            should_cut = duration_ms >= config.min_silence_ms
            if not should_cut:
                skip_reason = f"too short ({duration_ms:.0f}ms < {config.min_silence_ms}ms)"

        gaps.append(Gap(
            start=raw_start,
            end=gap_end,
            effective_start=effective_start,
            speech_end=speech_end,
            duration_ms=duration_ms,
            gap_type=gap_type,
            cut=should_cut,
            skip_reason=skip_reason,
        ))

    return gaps
