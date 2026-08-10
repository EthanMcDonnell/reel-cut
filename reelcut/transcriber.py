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
    return _transcribe_with_model(model, wav_path, config)


def _transcribe_with_model(model, wav_path: Path, config: WhisperConfig) -> list[WordTimestamp]:
    """Run transcription on an already-loaded WhisperModel."""
    segments, _ = model.transcribe(
        str(wav_path),
        language=config.language,
        word_timestamps=True,
        beam_size=config.beam_size,
        initial_prompt=config.initial_prompt,
        condition_on_previous_text=config.condition_on_previous_text,
        no_speech_threshold=config.no_speech_threshold,
        compression_ratio_threshold=config.compression_ratio_threshold,
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

    return _merge_leading_comma_tokens(words)


def _merge_leading_comma_tokens(words: list[WordTimestamp]) -> list[WordTimestamp]:
    """Merge BPE split tokens like ["30", ",000"] → ["30,000"].

    Whisper's tokenizer can produce a leading-comma token when a number like
    30,000 is split at the comma boundary.  Joining with a space would yield
    "30 ,000", so we merge them instead.
    """
    merged: list[WordTimestamp] = []
    for w in words:
        if merged and w.word.startswith(","):
            prev = merged[-1]
            merged[-1] = WordTimestamp(
                word=prev.word + w.word,
                start=prev.start,
                end=w.end,
                confidence=min(prev.confidence, w.confidence),
                clip_path=prev.clip_path,
            )
        else:
            merged.append(w)
    return merged


def align(
    words: list[WordTimestamp],
    wav_path: str | Path,
    config: WhisperConfig,
) -> tuple[list[WordTimestamp], str, list[dict]]:
    """Refine word timestamps via WhisperX wav2vec2 forced alignment.

    Numeric tokens (e.g. '732', '4') are expanded to their spoken form before
    alignment so wav2vec2 can locate them phonetically, then collapsed back
    afterward.  Any word that still can't be aligned falls back to its original
    Whisper timestamp.

    Returns (words, status_message, segments) where segments is the list of
    dicts fed to WhisperX (each has start, end, text). Empty on fallback paths.
    Caller is responsible for logging.
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
            min_conf = config.min_alignment_confidence
            # Collapse expanded tokens back to original words. Words that wav2vec2
            # returned with confidence below min_conf fall back to their Whisper
            # timestamps rather than being dropped — short function words ("at", "for")
            # routinely score just below the threshold despite being real.
            aligned = _collapse_expanded_words(expansion, aligned_flat, min_conf=min_conf)
            # Alignment can place a word before its predecessor (overlapping or
            # reordered timestamps), especially around numeric tokens at the tail
            # of a long segment. Repair any such non-monotonic output before it
            # drives a spurious mid-phrase cut downstream.
            aligned = _enforce_monotonic_timestamps(aligned, expansion)
            return aligned, f"WhisperX wav2vec2 ({device})", segments

    except ImportError:
        return words, "whisperx not installed — using Whisper timestamps", []
    except TimeoutError:
        return words, "WhisperX model load timed out — using Whisper timestamps", []
    except Exception as exc:
        return words, f"WhisperX failed ({type(exc).__name__}: {exc}) — using Whisper timestamps", []

    return words, "WhisperX returned no words — using Whisper timestamps", []


def filter_words_by_vad(
    words: list[WordTimestamp],
    wav_path: str | Path,
    threshold: float = 0.5,
    silence_threshold_db: float = -40.0,
    failure_tolerance_ratio: float = 0.02,
) -> list[WordTimestamp]:
    """Drop words that are both outside VAD-detected speech regions and silent.

    Uses Silero VAD via ONNX (no PyTorch) to find speech segments, then keeps
    any word whose midpoint lands inside a speech segment. Words Silero misses
    (short, quiet, or sentence-initial speech it clips at segment onset) are
    rescued if their audio window carries real energy — only words that are
    non-speech *and* silent are dropped as hallucinations.
    """
    import numpy as np
    import soundfile as sf
    from .vad import get_speech_timestamps

    wav_path = Path(wav_path)
    audio, sr = sf.read(str(wav_path), dtype="float32", always_2d=False)
    segments = get_speech_timestamps(audio, sr=sr, threshold=threshold)

    if not segments:
        return words

    threshold_linear = float(10 ** (silence_threshold_db / 20))

    kept: list[WordTimestamp] = []
    for w in words:
        mid = (w.start + w.end) / 2
        if any(seg["start"] <= mid <= seg["end"] for seg in segments):
            kept.append(w)
            continue
        # Silero missed it — rescue if the word's window has real sound.
        chunk = audio[int(w.start * sr) : int(w.end * sr)]
        if len(chunk) < 16 or float(np.mean(np.abs(chunk) > threshold_linear)) >= failure_tolerance_ratio:
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


def _reconcile_retranscribed(
    found: list["WordTimestamp"],
    words_replaced: list["WordTimestamp"],
    win_end: float,
    conf_threshold: float,
    rescue_floor: float = 0.05,
    regression_margin: float = 0.20,
) -> tuple[list["WordTimestamp"], list["WordTimestamp"]]:
    """Filter retranscribed words, rescuing below-floor words that both passes agreed on.

    Normal keep: in-bounds and confidence >= conf_threshold.
    Rescue: in-bounds, below conf_threshold, but the original pass found the same word
    (case-insensitive) at >= rescue_floor. Two independent passes agreeing is corroborating
    evidence even when both scores are low (e.g. words at sub-clip boundaries). Adopt the
    original's text + confidence while keeping the retrans timestamp. Returns (kept, rescued).

    Regression guard: retranscription exists to *improve* a suspicious region, but a short
    sub-clip strips the surrounding context Whisper needs and it can return a confident
    original as a different, less confident word ("Like"@0.78 → "Lie."@0.20, "API?"@0.86 →
    "IPL."@0.64). Where both passes produced the same word count — so position i in each
    refers to the same utterance — a retranscribed word that falls regression_margin below
    its original is reverted to the original's text + confidence, keeping the retrans
    timestamp exactly as the agreement rescue does. Improvements are never touched.
    """
    original_words = {
        w.word.lower(): w for w in words_replaced if w.confidence >= rescue_floor
    }
    kept: list[WordTimestamp] = []
    rescued: list[WordTimestamp] = []
    for w in found:
        if w.start >= win_end:
            continue
        if w.confidence >= conf_threshold:
            kept.append(w)
        elif w.word.lower() in original_words:
            orig = original_words[w.word.lower()]
            w.word = orig.word
            w.confidence = orig.confidence
            kept.append(w)
            rescued.append(w)

    if len(kept) == len(words_replaced):
        for w, orig in zip(kept, words_replaced):
            if orig.confidence - w.confidence >= regression_margin:
                w.word = orig.word
                w.confidence = orig.confidence
                rescued.append(w)
    return kept, rescued


def retranscribe_suspicious_regions(
    words: list[WordTimestamp],
    wav_path: str | Path,
    config: WhisperConfig,
    conf_threshold: float = 0.5,
    rescue_floor: float = 0.05,
    regression_margin: float = 0.20,
    clips_dir: Path | None = None,
    silence_threshold_db: float = -40.0,
    min_silence_ms: int = 200,
    failure_tolerance_ratio: float = 0.02,
    vad_threshold: float = 0.5,
    sentence_pause_s: float = 0.4,
) -> tuple[list[WordTimestamp], int, list[dict]]:
    """Detect and retranscribe suspicious audio regions to surface hidden false-start words.

    Three trigger types feed into a single merged-window pipeline:

    Case 1 — Wide word  (config: wide_word_threshold_s, default 1.0s)
        Whisper gives a word a suspiciously large span (e.g. "obviously," at 2.2s),
        spreading it across dead air or hidden speech. Window covers the full word span.
        Origin: false starts that Whisper collapsed into one transcript — the gap
        between a false-start attempt and the clean retry looks like one abnormally
        wide word.

    Case 2 — Low-confidence run + gap  (config: retranscribe_low_conf_gap_ms, default 500ms)
        A consecutive run of words all below conf_threshold followed by a gap ≥ the
        threshold. Low-confidence words near gaps are problematic: the gap detector's
        hard-floor rule suppresses cuts on any gap adjacent to a word below
        min_word_confidence regardless of duration. Retranscribing confirms whether
        the gap is dead air (boost confidence to unblock the cut) or contains speech.
        Window starts at the first word of the low-conf run.
        Origin: "for/the/account" (conf 0.49/0.45/0.22) blocking a 2.17s gap from
        being cut because "account"'s confidence fell below min_word_confidence.

    Case 3 — Large inter-word gap  (config: retranscribe_large_gap_ms, 0 = disabled)
        Any consecutive word pair with a gap ≥ the threshold regardless of confidence.
        A pause this long mid-speech often contains a false-start fragment that Whisper
        absorbed into a single transcript without surfacing it as a repeated phrase.
        Window covers only the gap itself (word.end → next_word.start).
        Origin: "or" ending at 89.9s → "Meta's" starting at 91.5s (1.6s gap), hiding
        a false-start fragment "or Met..." that Whisper never transcribed separately,
        leaving WhisperX alignment confused and "chatbot" dropped entirely.

    Case 4 — Low-confidence word
        Any single word below conf_threshold, regardless of span or adjacent gaps.
        Window covers the full word span [w.start, w.end]. Whisper probability below
        conf_threshold indicates genuine transcription uncertainty — retranscribing the
        region confirms or replaces the word with a proper window and log entry.

    Windows from all three triggers are collected, sorted, and merged before any audio
    is touched. Adjacent or overlapping windows from different trigger types chain into
    one larger window. Each window is then split at internal silences (silence_threshold_db,
    min_silence_ms, failure_tolerance_ratio) before transcription — forcing Whisper to treat
    each speech attempt independently rather than merging them into one fluent transcript.

    If retranscription finds words: replaces words in the window (or inserts into the
    gap when the window contains no existing words).
    If nothing found + window contained low-conf words: boosts the last low-conf word's
    confidence to 0.95 to unblock gap detection (confirmed dead air).
    If nothing found + pure gap or wide-word window: no change.

    Returns (updated_words, n_windows_processed). Call on raw Whisper words before
    align() — alignment then runs on the cleaned output, giving word-level precision
    to a transcript that no longer contains false starts or hidden speech regions.
    """
    import tempfile

    import numpy as np
    import soundfile as sf
    from faster_whisper import WhisperModel

    from .vad import get_speech_timestamps

    wav_path = Path(wav_path)
    audio, sample_rate = sf.read(str(wav_path), dtype="float32")

    wide_threshold_s = config.wide_word_threshold_s
    low_conf_gap_s = (config.retranscribe_low_conf_gap_ms / 1000
                      if config.retranscribe_low_conf_gap_ms > 0 else float("inf"))
    large_gap_s = (config.retranscribe_large_gap_ms / 1000
                   if config.retranscribe_large_gap_ms > 0 else float("inf"))

    # --- Collect windows from all three trigger types ---
    raw_windows: list[tuple[float, float, str]] = []  # (start_s, end_s, label)

    # Case 1: wide aligned words
    for w in words:
        if (w.end - w.start) >= wide_threshold_s:
            raw_windows.append((w.start, w.end, "wide"))

    # Case 2: low-confidence run followed by a large gap
    i = 0
    while i < len(words):
        if words[i].confidence < conf_threshold:
            run_start_i = i
            while i < len(words) and words[i].confidence < conf_threshold:
                i += 1
            run_end_i = i - 1
            if i < len(words):
                gap = words[i].start - words[run_end_i].end
                if gap >= low_conf_gap_s:
                    raw_windows.append((words[run_start_i].start, words[i].start, "low_conf"))
        else:
            i += 1

    # Case 3: large inter-word gap — mid-sentence only
    # Sentence-boundary gaps are expected at this stage (no silence cutting yet),
    # so skip any gap where the preceding word ends with sentence-ending punctuation.
    for i in range(len(words) - 1):
        gap = words[i + 1].start - words[i].end
        if gap >= large_gap_s and not words[i].word.rstrip().endswith(_TERMINAL_PUNCT):
            raw_windows.append((words[i].end, words[i + 1].start, "large_gap"))

    # Case 4: individual low-confidence word — catches hallucinations that are too short
    # or too isolated to trigger Cases 1–3. Prevents silent dropping during alignment
    # from stretching neighbors into spurious wide-word windows.
    # A low-conf word immediately after a gap is the signature of speech Whisper
    # dropped into that gap and mangled the boundary word (e.g. "fresh [out of the
    # oven] See," with "See," scoring 0.03). Reach back across the preceding gap so
    # the silence-splitter can isolate and recover the dropped phrase — even when the
    # gap is below the Case 3 large-gap floor. Anchor on the *previous word's start*,
    # not its end: inter-word timestamps are imprecise, so a window edge at words[i-1].end
    # lands mid-syllable and clips a half-word off the prior sentence. Feeding the
    # previous word's start to _expand_to_sentence carries the window edge out to the
    # enclosing sentence boundary, which is preceded by real silence — a clean cut.
    low_conf_gap_floor_s = config.retranscribe_low_conf_gap_floor_ms / 1000
    for i, w in enumerate(words):
        if w.confidence < conf_threshold:
            win_start = w.start
            if i > 0 and (w.start - words[i - 1].end) >= low_conf_gap_floor_s:
                win_start = words[i - 1].start
            raw_windows.append((win_start, w.end, "low_conf_word"))

    if not raw_windows:
        return list(words), 0, []

    # --- Expand each window to the enclosing sentence ---
    expansion_records: list[dict] = []
    for orig_start, orig_end, label in raw_windows:
        exp_start, exp_end, hard_capped = _expand_to_sentence(
            words, orig_start, orig_end,
            pause_threshold_s=sentence_pause_s,
        )
        expansion_records.append({
            "orig_start": orig_start,
            "orig_end": orig_end,
            "exp_start": exp_start,
            "exp_end": exp_end,
            "hard_capped": hard_capped,
            "label": label,
        })
    raw_windows = [(r["exp_start"], r["exp_end"], r["label"]) for r in expansion_records]

    # --- Merge overlapping / adjacent windows ---
    # Bridge gaps up to retranscribe_merge_gap_s so windows triggered by different
    # events across a short noise/retake boundary collapse into one Whisper pass.
    merged = _merge_retranscribe_windows(raw_windows, config.retranscribe_merge_gap_s)

    # --- Load model once for all windows ---
    device = "cuda" if config.compute_type == "float16" else "cpu"
    model = WhisperModel(
        config.model,
        compute_type=config.compute_type,
        device=device,
        cpu_threads=os.cpu_count() or 4,
    )
    retranscribe_config = config.model_copy(
        update={
            "no_speech_threshold": config.retranscribe_no_speech_threshold,
            "compression_ratio_threshold": config.retranscribe_compression_ratio_threshold,
        }
    )

    if clips_dir is not None:
        clips_dir.mkdir(parents=True, exist_ok=True)

    # --- Process windows right-to-left to preserve list indices ---
    result = list(words)
    retrans_log: list[dict] = []
    for win_start, win_end, label in reversed(merged):
        # Words whose start falls within [win_start, win_end)
        idx_start = next((i for i, w in enumerate(result) if w.start >= win_start), len(result))
        idx_end   = next((i for i, w in enumerate(result) if w.start >= win_end),   len(result))

        # Source clip: first word in window, falling back to word just before it
        if idx_start < len(result):
            source_clip = result[idx_start].clip_path
        elif idx_start > 0:
            source_clip = result[idx_start - 1].clip_path
        else:
            source_clip = words[0].clip_path if words else ""

        # Track low-conf indices for the confidence-boost fallback
        low_conf_in_window = [
            i for i in range(idx_start, idx_end)
            if result[i].confidence < conf_threshold
        ]
        words_replaced = [result[i] for i in range(idx_start, idx_end)]

        start_sample = int(win_start * sample_rate)
        end_sample   = int(win_end   * sample_rate)
        chunk = audio[start_sample:end_sample]
        # Whisper needs at least ~100ms of audio to produce meaningful output.
        if len(chunk) < int(sample_rate * 0.1):
            continue

        # Split window at internal silences so each speech attempt is transcribed
        # independently. Whisper collapses false starts in long continuous clips;
        # short clips that end at a silence boundary force it to be honest.
        sub_segs = _split_audio_at_silences(
            chunk, sample_rate,
            silence_threshold_db=silence_threshold_db,
            min_silence_ms=min_silence_ms,
            failure_tolerance_ratio=failure_tolerance_ratio,
        )

        if clips_dir is not None:
            sf.write(str(clips_dir / f"{label}_{win_start:.3f}.wav"), chunk, sample_rate)

        found_raw: list[WordTimestamp] = []
        sub_clips_log: list[dict] = []
        for seg_i, (sub_start_s, sub_end_s) in enumerate(sub_segs):
            sub_start_sample = int(sub_start_s * sample_rate)
            sub_end_sample   = int(sub_end_s   * sample_rate)
            sub_chunk = chunk[sub_start_sample:sub_end_sample]
            if len(sub_chunk) < int(sample_rate * 0.1):
                continue

            if clips_dir is not None:
                sub_path = clips_dir / f"{label}_{win_start:.3f}_sub{seg_i}.wav"
                cleanup_sub = False
                sf.write(str(sub_path), sub_chunk, sample_rate)
            else:
                sub_path = None
                cleanup_sub = False

            # Skip sub-clips with no detectable audio energy so Whisper doesn't
            # hallucinate on breath sounds or noise between speech attempts.
            # Uses the same amplitude + tolerance logic as _split_audio_at_silences.
            _mono = sub_chunk if sub_chunk.ndim == 1 else sub_chunk.mean(axis=1)
            _thr = float(10 ** (silence_threshold_db / 20))
            _frame = max(1, int(sample_rate * 0.01))
            _n_frames = len(_mono) // _frame
            _active = sum(
                float(np.mean(np.abs(_mono[i*_frame:(i+1)*_frame]) > _thr)) >= failure_tolerance_ratio
                for i in range(_n_frames)
            )
            if _n_frames > 0 and _active / _n_frames < 0.05:
                sub_clips_log.append({"start_s": sub_start_s, "end_s": sub_end_s, "words": []})
                continue

            # Amplitude alone can't distinguish a loud breath from speech, so a
            # breath between takes clears the energy gate above and Whisper
            # hallucinates words over it (e.g. a URL). Silero VAD is purpose-built
            # for speech-vs-breath; skip sub-clips it finds no speech in.
            try:
                if not get_speech_timestamps(_mono, sr=sample_rate, threshold=vad_threshold):
                    sub_clips_log.append({"start_s": sub_start_s, "end_s": sub_end_s, "words": []})
                    continue
            except Exception:
                pass  # VAD unavailable — fall back to the amplitude gate only

            if sub_path is None:
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                    sub_path = Path(f.name)
                cleanup_sub = True

            try:
                if cleanup_sub:
                    sf.write(str(sub_path), sub_chunk, sample_rate)
                sub_words = _transcribe_with_model(model, sub_path, retranscribe_config)
                sub_clip_found: list[WordTimestamp] = []
                for w in sub_words:
                    wt = WordTimestamp(
                        word=w.word,
                        start=w.start + sub_start_s,
                        end=w.end + sub_start_s,
                        confidence=w.confidence,
                        clip_path=w.clip_path,
                    )
                    found_raw.append(wt)
                    sub_clip_found.append(wt)
                sub_clips_log.append({"start_s": sub_start_s, "end_s": sub_end_s, "words": sub_clip_found})
            except Exception:
                sub_clips_log.append({"start_s": sub_start_s, "end_s": sub_end_s, "words": []})
            finally:
                if cleanup_sub:
                    sub_path.unlink(missing_ok=True)

        # Copy words before mutating so found_raw preserves clip-relative timestamps
        # for the debug log (the log shows these as-found before offset is applied).
        found = [
            WordTimestamp(
                word=w.word, start=w.start, end=w.end,
                confidence=w.confidence, clip_path=w.clip_path,
            )
            for w in found_raw
        ]
        found_rescued: list[WordTimestamp] = []
        if found:
            for w in found:
                w.start += win_start
                w.end    = min(w.end + win_start, win_end)  # clamp to window boundary
                w.clip_path = source_clip
            # Filter to window bounds and drop low-confidence words. Whisper often
            # bleeds the tail of the preceding word into the first ~100ms of a short
            # clip, producing a ghost low-conf duplicate. Those words hard-floor gap
            # detection, blocking cuts near the window boundary. Dropping them here
            # mirrors the confidence floor applied everywhere else in the pipeline.
            # Rescue exception: a below-floor word is kept when both passes agree on
            # it case-insensitively and the original was confident — casing ambiguity
            # from clip isolation can depress the score without reflecting true
            # acoustic uncertainty.
            found, found_rescued = _reconcile_retranscribed(
                found, words_replaced, win_end, conf_threshold, rescue_floor,
                regression_margin,
            )

        # Derive dropped words from found_raw (clip-relative timestamps, before offset).
        # Rescued words are excluded — they survived the filter via cross-pass agreement.
        rescued_lower = {w.word.lower() for w in found_rescued}
        found_dropped = [
            w for w in found_raw
            if (w.start + win_start) >= win_end
            or (w.confidence < conf_threshold and w.word.lower() not in rescued_lower)
        ]

        # Re-check after filtering: retranscription may have returned only low-conf
        # bleed words that were all dropped above.
        if found:
            result[idx_start:idx_end] = found
            action = "replaced"
        elif low_conf_in_window:
            # Nothing usable found + low-conf words present → confirmed dead air.
            # Boost last low-conf word's confidence to unblock gap detection.
            result[low_conf_in_window[-1]].confidence = 0.95
            action = "boosted"
        else:
            action = "no_change"

        # Expansion records whose expanded range overlaps this merged window
        window_exp = [
            r for r in expansion_records
            if r["exp_start"] < win_end and r["exp_end"] > win_start
        ]
        pre_exp_start = min((r["orig_start"] for r in window_exp), default=win_start)
        pre_exp_end   = max((r["orig_end"]   for r in window_exp), default=win_end)
        hard_capped   = any(r["hard_capped"] for r in window_exp)

        retrans_log.append({
            "win_start": win_start,
            "win_end": win_end,
            "pre_exp_start": pre_exp_start,
            "pre_exp_end": pre_exp_end,
            "hard_capped": hard_capped,
            "label": label,
            "before": words_replaced,
            "found_raw": found_raw,
            "found_kept": found,
            "found_dropped": found_dropped,
            "found_rescued": found_rescued,
            "action": action,
            "sub_clips": sub_clips_log,
        })

    return result, len(merged), retrans_log


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
    min_conf: float = 0.0,
) -> list[WordTimestamp]:
    """Collapse WhisperX-aligned expanded tokens back to original words.

    For each original word:
    - Non-numeric (n=1): if the current aligned token matches by text AND its
      confidence is >= min_conf, use its timestamp.  If the word is absent or
      its confidence is too low, restore from the original Whisper timestamp so
      the word isn't silently dropped (short function words like "at"/"for" often
      align below threshold despite being real speech).
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
            # Non-numeric word — take the aligned token if text matches and confidence
            # is acceptable; otherwise restore the original Whisper timestamp.
            if (ai < len(aligned)
                    and _norm_word(aligned[ai].word) == _norm_word(exp.tokens[0])
                    and aligned[ai].confidence >= min_conf):
                w = aligned[ai]
                ai += 1
                result.append(WordTimestamp(
                    word=orig.word, start=w.start, end=w.end,
                    confidence=w.confidence, clip_path=orig.clip_path,
                ))
            else:
                # Absent or low-confidence alignment — restore Whisper timestamp.
                # Advance ai past a matching-but-low-confidence token so later words
                # don't consume it.
                if (ai < len(aligned)
                        and _norm_word(aligned[ai].word) == _norm_word(exp.tokens[0])):
                    ai += 1
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


def _enforce_monotonic_timestamps(
    collapsed: list[WordTimestamp],
    expansion: list[_Expansion],
) -> list[WordTimestamp]:
    """Repair non-monotonic alignment output.

    WhisperX occasionally places a word before its predecessor — overlapping or
    reordered timestamps, seen most often around numeric tokens near the tail of
    a long segment. `_collapse_expanded_words` restores some words to their
    pre-align Whisper timestamps while neighbours keep corrupted aligned ones, so
    the collapsed sequence can come out overlapping or out of order. That reads
    downstream as a sentence-ending word followed by a gap, which triggers a
    spurious cut through the middle of the phrase.

    Wherever a word starts before the previous word ends, fall it back to its
    pre-align (Whisper) timestamp, which is monotonic by construction. `collapsed`
    is 1:1 with `expansion`, so each word's original is `exp.orig_word`.

    Falling back only the later word cannot fix an inversion caused by the
    *earlier* word being aligned too late — the restored original then sits
    before a predecessor that keeps its corrupted timestamp, leaving the pair out
    of order. So walk back over any predecessor still ahead of the fallback and
    restore its original too; originals are monotonic by construction, so the run
    is ordered once the walk stops.
    """
    result: list[WordTimestamp] = []
    prev_end = float("-inf")
    for i, (w, exp) in enumerate(zip(collapsed, expansion)):
        if w.start < prev_end:
            w = exp.orig_word
            j = i - 1
            while j >= 0 and w.start < result[j].end:
                result[j] = expansion[j].orig_word
                j -= 1
        result.append(w)
        prev_end = w.end
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

def _merge_retranscribe_windows(
    raw_windows: list[tuple[float, float, str]],
    merge_gap_s: float,
) -> list[tuple[float, float, str]]:
    """Merge retranscription windows that overlap or are within merge_gap_s of each other."""
    sorted_windows = sorted(raw_windows, key=lambda x: x[0])
    merged: list[tuple[float, float, str]] = []
    for start, end, label in sorted_windows:
        if merged and start <= merged[-1][1] + merge_gap_s:
            prev_start, prev_end, prev_label = merged[-1]
            combined = prev_label if label in prev_label else f"{prev_label}+{label}"
            merged[-1] = (prev_start, max(prev_end, end), combined)
        else:
            merged.append((start, end, label))
    return merged


def _norm_word(w: str) -> str:
    """Lowercase + strip trailing punctuation for word matching."""
    return w.strip().lower().rstrip(".,!?;:'\"")


# Sentence-terminal punctuation — the single set used everywhere a sentence
# boundary is decided (captions, EDL cut permission, alignment windowing).
_TERMINAL_PUNCT = (".", "!", "?")

# Clause-terminal punctuation — a natural pause within a sentence. Used only
# for EDL cut permission (a comma pause is a safe place to remove silence),
# never for caption line splits.
_CLAUSE_PUNCT = (",", ";", ":")

# Default minimum pause (seconds) before a capitalised word that marks a
# sentence boundary Whisper failed to punctuate. Within-sentence inter-word
# gaps are typically well under this; requiring a real pause keeps mid-sentence
# proper nouns from triggering a false boundary.
SENTENCE_PAUSE_S = 0.4


def is_sentence_boundary(
    curr_word: str,
    next_word: str | None,
    gap_s: float,
    pause_threshold_s: float = SENTENCE_PAUSE_S,
    include_clause: bool = False,
) -> bool:
    """True if a sentence boundary falls after curr_word.

    Single source of truth for sentence segmentation. Signals:
    - explicit terminal punctuation on curr_word ('.', '!', '?');
    - a capitalised next_word following a pause >= pause_threshold_s, which
      recovers boundaries Whisper left unpunctuated (full stops it omits are
      far less consistent than the capitalisation that opens the next sentence); and
    - with include_clause=True, clause punctuation (',', ';', ':') — a safe
      pause to cut silence at, used for EDL cut permission only.
    """
    end = curr_word.rstrip()
    if end.endswith(_TERMINAL_PUNCT):
        return True
    if include_clause and end.endswith(_CLAUSE_PUNCT):
        return True
    if next_word and next_word[:1].isupper() and gap_s >= pause_threshold_s:
        return True
    return False


def _find_sentence_end(
    words: list[WordTimestamp],
    from_idx: int,
    origin_idx: int,
    caps_floor_s: float,
    hard_cap_s: float,
) -> int:
    """Return the index of the last word in the sentence, scanning forward from from_idx.

    Stops at the first fullstop/questionmark (primary). A capitalised word triggers
    an early split — returning i-1 — only when elapsed time from origin_idx meets the
    caps/hard-cap thresholds (see _caps_split). Falls back to the last word if neither
    condition fires.
    """
    result = len(words) - 1
    for i in range(from_idx, len(words)):
        if words[i].word.rstrip().endswith(_TERMINAL_PUNCT):
            result = i
            break
        if i > from_idx:
            elapsed = words[i].start - words[origin_idx].start
            if _caps_split(words[i].word, elapsed, caps_floor_s, hard_cap_s):
                result = i - 1
                break
    return result


def _caps_split(word: str, elapsed_s: float, caps_floor_s: float, hard_cap_s: float) -> bool:
    """True when elapsed_s warrants splitting before this word.

    Caps trigger fires when elapsed_s >= caps_floor_s and the word is capitalised.
    Hard cap fires at hard_cap_s regardless of capitalisation.
    """
    is_caps = bool(word and word[0].isupper())
    return (elapsed_s >= caps_floor_s and is_caps) or elapsed_s >= hard_cap_s


def _words_to_whisperx_segments(words: list[WordTimestamp]) -> list[dict]:
    """Group words into segments for whisperx alignment input.

    Splits at sentence-ending punctuation (primary) with a max duration cap
    (fallback) so CTC search windows match natural speech phrases.
    """
    if not words:
        return []

    MIN_WORDS = 3

    segments = []
    chunk_start = 0
    i = 0

    while i < len(words):
        end_idx = _find_sentence_end(words, i, chunk_start, caps_floor_s=10.0, hard_cap_s=20.0)
        i = end_idx + 1
        chunk = words[chunk_start:i]
        if len(chunk) >= MIN_WORDS:
            segments.append({
                "start": chunk[0].start,
                "end": chunk[-1].end,
                "text": " ".join(w.word for w in chunk),
            })
            chunk_start = i

    if chunk_start < len(words):
        remaining = words[chunk_start:]
        segments.append({
            "start": remaining[0].start,
            "end": remaining[-1].end,
            "text": " ".join(w.word for w in remaining),
        })

    return segments


def _expand_to_sentence(
    words: list[WordTimestamp],
    win_start: float,
    win_end: float,
    max_duration_s: float = 20.0,
    pause_threshold_s: float = SENTENCE_PAUSE_S,
) -> tuple[float, float, bool]:
    """Expand a retranscription window outward to the enclosing sentence boundaries.

    Scans backward from win_start for the nearest genuine sentence start (a
    capitalised word preceded by terminal punctuation or a pause >=
    pause_threshold_s) and forward from win_end for the nearest terminal punct.
    A capitalised word is only used as a fallback split point when the window
    would exceed max_duration_s. Total duration capped at max_duration_s.

    Returns (exp_start, exp_end, hard_capped) where hard_capped is True if the
    20s cap was the binding constraint (sentence was longer than max_duration_s).
    """
    if not words:
        return win_start, win_end, False

    # Index of first word at or after win_start
    anchor_start_idx = next(
        (i for i, w in enumerate(words) if w.start >= win_start),
        len(words) - 1,
    )
    # Index of last word whose start falls before win_end
    anchor_end_idx = next(
        (i for i in range(len(words) - 1, -1, -1) if words[i].start < win_end),
        anchor_start_idx,
    )

    # Scan backward: find the nearest genuine sentence start using the shared
    # is_sentence_boundary predicate so expansion and the 1b debug always agree.
    sent_start_idx = anchor_start_idx
    for i in range(anchor_start_idx, -1, -1):
        if not (words[i].word and words[i].word[0].isupper()):
            continue
        if i == 0 or is_sentence_boundary(
            words[i - 1].word, words[i].word,
            words[i].start - words[i - 1].end,
            pause_threshold_s,
        ):
            sent_start_idx = i
            break

    # Scan forward to the sentence end using the shared helper
    sent_end_idx = _find_sentence_end(
        words, anchor_end_idx, sent_start_idx,
        caps_floor_s=max_duration_s, hard_cap_s=max_duration_s,
    )

    # Clamp so expansion only ever grows the requested window, never shrinks it.
    # The backward scan stops at the first capitalised word; when the flagged word
    # is itself capitalised (Whisper's spurious mid-utterance sentence boundary),
    # sent_start_idx lands on it and words[sent_start_idx].start can fall *after*
    # win_start — which would drop a preceding gap the caller deliberately included.
    exp_start = min(words[sent_start_idx].start, win_start)
    natural_end = max(words[sent_end_idx].end, win_end)
    hard_capped = natural_end > exp_start + max_duration_s
    exp_end = min(natural_end, exp_start + max_duration_s)

    # The cap can land mid-word. retranscribe_suspicious_regions replaces every
    # word whose *start* falls inside the window, so a word straddling exp_end is
    # deleted from the transcript while Whisper only ever sees its opening
    # fragment — the word is lost outright. Snap the cap back to the last word
    # that fits entirely, which pushes the straddler's start to exp_end and out
    # of the replaced range.
    if hard_capped:
        fits = [w.end for w in words if exp_start < w.end <= exp_end]
        if fits:
            exp_end = max(fits)

    return exp_start, exp_end, hard_capped


def _split_audio_at_silences(
    audio: "np.ndarray",
    sample_rate: int,
    silence_threshold_db: float,
    min_silence_ms: int,
    failure_tolerance_ratio: float,
) -> list[tuple[float, float]]:
    """Split audio into speech segments at qualifying silence gaps.

    Uses the same amplitude + failure_tolerance_ratio logic as the main gap
    detector. Returns a list of (start_s, end_s) pairs — one per speech segment.
    Returns a single full-duration segment when no qualifying silence is found,
    so callers can always iterate unconditionally.
    """
    import numpy as np

    threshold_linear = float(10 ** (silence_threshold_db / 20))
    frame_size = max(1, int(sample_rate * 0.01))          # 10ms frames
    min_silence_frames = max(1, min_silence_ms // 10)      # in 10ms units
    total_dur = len(audio) / sample_rate

    n_frames = len(audio) // frame_size
    if n_frames < 2:
        return [(0.0, total_dur)]

    # Classify each 10ms frame as silent or not
    is_silent: list[bool] = []
    for i in range(n_frames):
        chunk = audio[i * frame_size:(i + 1) * frame_size]
        fraction_above = float(np.mean(np.abs(chunk) > threshold_linear))
        is_silent.append(fraction_above < failure_tolerance_ratio)

    # Find silence runs long enough to act as split points.
    # Store (silence_start_sample, silence_end_sample) so sub-clips are bounded
    # to speech regions and don't include silence-only segments at their edges.
    silence_regions: list[tuple[int, int]] = []
    i = 0
    while i < len(is_silent):
        if is_silent[i]:
            run_start = i
            while i < len(is_silent) and is_silent[i]:
                i += 1
            run_len = i - run_start
            if run_len >= min_silence_frames:
                silence_regions.append((run_start * frame_size, i * frame_size))
        else:
            i += 1

    if not silence_regions:
        return [(0.0, total_dur)]

    # Build speech segments between silence boundaries, excluding silence itself.
    seg_starts = [0] + [end for _, end in silence_regions]
    seg_ends   = [start for start, _ in silence_regions] + [len(audio)]
    segs = [
        (s / sample_rate, e / sample_rate)
        for s, e in zip(seg_starts, seg_ends)
        if e > s
    ]
    return segs if segs else [(0.0, total_dur)]
