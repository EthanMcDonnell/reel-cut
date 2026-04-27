"""Transcriber — faster-whisper + WhisperX wav2vec2 forced alignment."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import WhisperConfig

# Set once at module load — prevents OMP deadlock after faster-whisper (PyTorch #17199).
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
    )

    segments, _ = model.transcribe(
        str(wav_path),
        language=config.language,
        word_timestamps=True,
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
) -> list[WordTimestamp]:
    """Refine word timestamps via WhisperX wav2vec2 forced alignment.

    Falls back to faster-whisper word timestamps if whisperx is unavailable
    or the alignment model can't be loaded (e.g. Intel Mac / no GPU).
    """
    wav_path = Path(wav_path)
    device = "cuda" if config.compute_type == "float16" else "cpu"

    try:
        import whisperx

        print(f"[align] Loading audio ({wav_path.name})...", flush=True)
        audio = whisperx.load_audio(str(wav_path))

        segments = _words_to_whisperx_segments(words)
        print(f"[align] Loading wav2vec2 alignment model on {device}...", flush=True)

        import signal

        _has_sigalrm = hasattr(signal, "SIGALRM")
        if _has_sigalrm:
            def _timeout(signum, frame):
                raise TimeoutError("load_align_model timed out")
            signal.signal(signal.SIGALRM, _timeout)
            signal.alarm(30)  # 30s timeout for model load
        try:
            alignment_model, metadata = whisperx.load_align_model(
                language_code=config.language,
                device=device,
            )
        finally:
            if _has_sigalrm:
                signal.alarm(0)

        print(f"[align] Running alignment on {len(segments)} segments...", flush=True)
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
            print(f"[align] Done — {len(aligned)} words aligned.", flush=True)
            return aligned

    except (ImportError, TimeoutError, Exception) as exc:
        print(f"[align] Skipping whisperx alignment ({type(exc).__name__}: {exc}). "
              f"Using faster-whisper word timestamps.", flush=True)

    return words


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
