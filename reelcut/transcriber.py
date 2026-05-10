"""Transcriber — faster-whisper + WhisperX wav2vec2 forced alignment."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

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
        initial_prompt=config.initial_prompt,
        condition_on_previous_text=config.condition_on_previous_text,
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

    Numeric tokens (e.g. '732', '4') are expanded to their spoken form before
    alignment so wav2vec2 can locate them phonetically, then collapsed back
    afterward.  Any word that still can't be aligned falls back to its original
    Whisper timestamp.

    Returns (words, status_message) — caller is responsible for logging.
    Falls back to faster-whisper word timestamps if whisperx is unavailable
    or the alignment model can't be loaded (e.g. Intel Mac / no GPU).
    """
    wav_path = Path(wav_path)
    device = "cuda" if config.compute_type == "float16" else "cpu"

    try:
        import whisperx

        audio = whisperx.load_audio(str(wav_path))

        # Expand numeric tokens to spoken form so wav2vec2 can align them.
        expanded_words, expansion = _expand_numeric_words(words)
        segments = _words_to_whisperx_segments(expanded_words)

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

        aligned_flat: list[WordTimestamp] = []
        for segment in result.get("segments", []):
            for w in segment.get("words", []):
                aligned_flat.append(WordTimestamp(
                    word=w.get("word", "").strip(),
                    start=w.get("start", 0.0),
                    end=w.get("end", 0.0),
                    confidence=w.get("score", 1.0),
                    clip_path=str(wav_path),
                ))

        if aligned_flat:
            # Drop alignment failures: wav2vec2 returns start=end=0 for words it
            # could not locate in the audio. These break gap detection when sorted.
            aligned_flat = [w for w in aligned_flat if not (w.start == 0.0 and w.end == 0.0)]
            # Collapse expanded tokens back to original words, falling back to
            # Whisper timestamps for any word that still couldn't be aligned.
            aligned = _collapse_expanded_words(expansion, aligned_flat)
            # Drop words where alignment confidence is too low — these are typically
            # Whisper hallucinations that wav2vec2 couldn't locate in the audio.
            min_conf = config.min_alignment_confidence
            if min_conf > 0:
                aligned = [w for w in aligned if w.confidence >= min_conf]
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
# Numeric expansion / collapse for WhisperX alignment
# ---------------------------------------------------------------------------

class _Expansion(NamedTuple):
    orig_word: WordTimestamp
    tokens: list[str]   # spoken-form tokens (same as [orig_word.word] if not numeric)


def _expand_numeric_words(
    words: list[WordTimestamp],
) -> tuple[list[WordTimestamp], list[_Expansion]]:
    """Replace numeric word tokens with their spoken-form equivalents.

    Returns a flat list of WordTimestamp objects (one per spoken token) and
    an expansion record for each original word so the results can be collapsed
    back after WhisperX alignment.  Non-numeric words are passed through unchanged
    with a single-element token list.
    """
    expanded: list[WordTimestamp] = []
    expansion: list[_Expansion] = []

    for w in words:
        tokens = _spoken_tokens(w.word)
        expansion.append(_Expansion(orig_word=w, tokens=tokens))

        n = len(tokens)
        if n == 1:
            expanded.append(w)
        else:
            # Distribute the original Whisper duration evenly across tokens so
            # WhisperX has a reasonable starting window for each spoken sub-word.
            dur = (w.end - w.start) / n
            for j, tok in enumerate(tokens):
                expanded.append(WordTimestamp(
                    word=tok,
                    start=w.start + j * dur,
                    end=w.start + (j + 1) * dur,
                    confidence=w.confidence,
                    clip_path=w.clip_path,
                ))

    return expanded, expansion


def _collapse_expanded_words(
    expansion: list[_Expansion],
    aligned: list[WordTimestamp],
) -> list[WordTimestamp]:
    """Collapse WhisperX-aligned expanded tokens back to original words.

    For each original word:
    - Non-numeric (n=1): if the current aligned token matches by text, use its
      timestamp; otherwise the word was dropped — restore from original Whisper.
    - Numeric (n>1): greedily consume aligned tokens that match the expected spoken
      sub-words in sequence.  Any sub-words that were dropped by wav2vec2 are
      skipped.  If at least one sub-word aligned, the span of the matched tokens
      becomes the word's timestamp; otherwise fall back to the original timestamp.
    """
    result: list[WordTimestamp] = []
    ai = 0  # current position in aligned

    for exp in expansion:
        orig = exp.orig_word
        n = len(exp.tokens)

        if n == 1:
            # Non-numeric word — take the aligned token if text matches.
            if ai < len(aligned) and _norm_word(aligned[ai].word) == _norm_word(exp.tokens[0]):
                w = aligned[ai]
                ai += 1
                result.append(WordTimestamp(
                    word=orig.word, start=w.start, end=w.end,
                    confidence=w.confidence, clip_path=orig.clip_path,
                ))
            else:
                # Dropped by WhisperX — restore Whisper timestamp, don't advance ai.
                result.append(orig)
        else:
            # Numeric word expanded to n tokens — consume matching tokens greedily.
            batch: list[WordTimestamp] = []
            tmp_ai = ai
            for tok in exp.tokens:
                if tmp_ai < len(aligned) and _norm_word(aligned[tmp_ai].word) == _norm_word(tok):
                    batch.append(aligned[tmp_ai])
                    tmp_ai += 1
                # else: this sub-word was dropped by wav2vec2 — skip it.

            if batch:
                ai = tmp_ai
                confidence = sum(b.confidence for b in batch) / len(batch)
                result.append(WordTimestamp(
                    word=orig.word,
                    start=batch[0].start,
                    end=batch[-1].end,
                    confidence=confidence,
                    clip_path=orig.clip_path,
                ))
            else:
                # Nothing aligned at all — restore original Whisper timestamp.
                result.append(orig)

    return result


# ---------------------------------------------------------------------------
# Number → spoken tokens
# ---------------------------------------------------------------------------

_ONES = [
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
    "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
    "sixteen", "seventeen", "eighteen", "nineteen",
]
_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]


def _int_to_words(n: int) -> str:
    """Convert a non-negative integer ≤ 999,999 to its English spoken form."""
    if n < 0:
        return "negative " + _int_to_words(-n)
    if n < 20:
        return _ONES[n]
    if n < 100:
        tens = _TENS[n // 10]
        ones = _ONES[n % 10] if n % 10 else ""
        return tens + (" " + ones if ones else "")
    if n < 1_000:
        rest = n % 100
        return _ONES[n // 100] + " hundred" + (" " + _int_to_words(rest) if rest else "")
    if n < 1_000_000:
        rest = n % 1_000
        return _int_to_words(n // 1_000) + " thousand" + (" " + _int_to_words(rest) if rest else "")
    return str(n)  # fallback for very large numbers


def _spoken_tokens(word: str) -> list[str]:
    """Return the spoken-form token list for a word.

    Purely numeric tokens (optionally prefixed by '-' and/or suffixed by
    punctuation, e.g. '-2026', '732', '-31431,') are converted to English
    words.  All other tokens are returned unchanged as a single-element list.
    """
    stripped = word.strip()
    core = stripped.lstrip("-").rstrip(".,!?;:\"'")
    if not core or not core.isdigit():
        return [word]
    try:
        spoken = _int_to_words(int(core))
        return spoken.split()
    except (ValueError, OverflowError):
        return [word]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _norm_word(w: str) -> str:
    """Lowercase + strip trailing punctuation for word matching."""
    return w.strip().lower().rstrip(".,!?;:'\"")


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
