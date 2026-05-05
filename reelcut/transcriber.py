"""Transcriber — faster-whisper + WhisperX wav2vec2 forced alignment."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from .config import WhisperConfig

logging.getLogger("faster_whisper").setLevel(logging.WARNING)
logging.getLogger("whisperx").setLevel(logging.WARNING)

# Prevents OMP deadlock after faster-whisper loads CTranslate2 (PyTorch #17199).
try:
    import torch
    torch.set_num_threads(1)
except ImportError:
    pass


@dataclass
class WordTimestamp:
    word: str
    start: float   # seconds
    end: float     # seconds
    confidence: float = 1.0
    clip_path: str = ""  # source clip, used in multi-clip workflows
    keep: bool = True    # False = outtake or retake; set by EDL construction


def transcribe(wav_path: str | Path, config: WhisperConfig) -> list[WordTimestamp]:
    """Transcribe a WAV file using faster-whisper with Silero VAD pre-filtering.

    Returns a list of WordTimestamp objects with segment-level timing.
    Alignment to word-level precision is done in align().
    """
    from faster_whisper import WhisperModel

    wav_path = Path(wav_path)
    if not wav_path.exists():
        raise FileNotFoundError(f"WAV file not found: {wav_path}")

    device = "cuda" if config.compute_type == "float16" else "cpu"
    model = WhisperModel(
        config.model,
        compute_type=config.compute_type,
        device=device,
        cpu_threads=os.cpu_count() or 4,
    )

    segments, _ = model.transcribe(
        str(wav_path),
        language=config.language,
        word_timestamps=True,
        beam_size=config.beam_size,
        vad_filter=False,         # disabled: Silero VAD (PyTorch) conflicts with CTranslate2 OpenMP on macOS
    )

    words: list[WordTimestamp] = []
    for segment in segments:
        if segment.words is None:
            continue
        for w in segment.words:
            words.append(WordTimestamp(
                word=w.word.strip(),
                start=w.start,
                end=w.end,
                confidence=w.probability,
                clip_path=str(wav_path),
            ))

    return words


def align(
    words: list[WordTimestamp],
    wav_path: str | Path,
    config: WhisperConfig,
) -> tuple[list[WordTimestamp], str]:
    """Refine word timestamps via WhisperX wav2vec2 forced alignment.

    Returns (words, status_message) — caller is responsible for logging.
    Falls back to faster-whisper word timestamps if whisperx is unavailable
    or the alignment model can't be loaded (e.g. Intel Mac / no GPU).
    """
    wav_path = Path(wav_path)
    device = "cuda" if config.compute_type == "float16" else "cpu"

    try:
        import whisperx

        audio = whisperx.load_audio(str(wav_path))
        segments = _words_to_whisperx_segments(words)

        import signal
        _has_sigalrm = hasattr(signal, "SIGALRM")
        if _has_sigalrm:
            def _timeout(signum, frame):
                raise TimeoutError("load_align_model timed out")
            signal.signal(signal.SIGALRM, _timeout)
            signal.alarm(30)
        try:
            alignment_model, metadata = whisperx.load_align_model(
                language_code=config.language,
                device=device,
            )
        finally:
            if _has_sigalrm:
                signal.alarm(0)

        result = whisperx.align(
            segments, alignment_model, metadata, audio, device,
            return_char_alignments=False,
        )

        aligned: list[WordTimestamp] = []
        for segment in result.get("segments", []):
            for w in segment.get("words", []):
                aligned.append(WordTimestamp(
                    word=w.get("word", "").strip(),
                    start=w.get("start", 0.0),
                    end=w.get("end", 0.0),
                    confidence=w.get("score", 1.0),
                    clip_path=str(wav_path),
                ))

        if aligned:
            # Drop alignment failures: wav2vec2 returns start=end=0 for words it
            # could not locate in the audio. These break gap detection when sorted.
            aligned = [w for w in aligned if not (w.start == 0.0 and w.end == 0.0)]
            return aligned, f"WhisperX wav2vec2 ({device})"

    except ImportError:
        return words, "whisperx not installed — using Whisper timestamps"
    except TimeoutError:
        return words, "WhisperX model load timed out — using Whisper timestamps"
    except Exception as exc:
        return words, f"WhisperX failed ({type(exc).__name__}: {exc}) — using Whisper timestamps"

    return words, "WhisperX returned no words — using Whisper timestamps"


def filter_words_by_vad(
    words: list[WordTimestamp],
    wav_path: str | Path,
    threshold: float = 0.5,
) -> list[WordTimestamp]:
    """Drop words that fall outside VAD-detected speech regions.

    Uses Silero VAD via ONNX (no PyTorch) to find speech segments, then
    keeps only words whose midpoint lands inside a speech segment.
    """
    import soundfile as sf
    from .vad import get_speech_timestamps

    wav_path = Path(wav_path)
    audio, sr = sf.read(str(wav_path), dtype="float32", always_2d=False)
    segments = get_speech_timestamps(audio, sr=sr, threshold=threshold)

    if not segments:
        return words

    kept: list[WordTimestamp] = []
    for w in words:
        mid = (w.start + w.end) / 2
        if any(seg["start"] <= mid <= seg["end"] for seg in segments):
            kept.append(w)

    return kept


def filter_silent_words(
    words: list[WordTimestamp],
    wav_path: str | Path,
    silence_threshold_db: float = -40.0,
    failure_tolerance_ratio: float = 0.02,
) -> list[WordTimestamp]:
    """Drop words whose audio window is below the noise floor.

    Whisper hallucinates words over silence/breathing when VAD is disabled.
    Uses the same failure-tolerance logic as the gap detector: a word is kept
    only if at least `failure_tolerance_ratio` of its samples exceed the threshold.
    """
    import numpy as np
    import soundfile as sf

    wav_path = Path(wav_path)
    audio, sr = sf.read(str(wav_path), dtype="float32", always_2d=False)
    threshold_linear = float(10 ** (silence_threshold_db / 20))

    kept: list[WordTimestamp] = []
    for w in words:
        start_sample = int(w.start * sr)
        end_sample = int(w.end * sr)
        chunk = audio[start_sample:end_sample]
        if len(chunk) < 16:
            kept.append(w)
            continue
        fraction_above = float(np.mean(np.abs(chunk) > threshold_linear))
        if fraction_above >= failure_tolerance_ratio:
            kept.append(w)

    return kept


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _words_to_whisperx_segments(words: list[WordTimestamp]) -> list[dict]:
    """Group words into segments for whisperx alignment input."""
    if not words:
        return []

    # Simple grouping: one segment per ~10 words
    group_size = 10
    segments = []
    for i in range(0, len(words), group_size):
        chunk = words[i : i + group_size]
        segments.append({
            "start": chunk[0].start,
            "end": chunk[-1].end,
            "text": " ".join(w.word for w in chunk),
        })
    return segments
