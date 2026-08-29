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
    speech_onset: float = 0.0  # true onset of the following word's speech, <= end — earlier
                           # than end when Whisper starts the word late. edl.py cuts up to
                           # here (minus pad) so word heads aren't clipped. Defaults to
                           # `end`, i.e. trusting the timestamp, which is the behaviour
                           # everywhere the alignment is confident.
    skip_reason: str = ""  # non-empty when cut=False; human-readable explanation

    def __post_init__(self) -> None:
        if self.speech_onset <= 0.0:
            self.speech_onset = self.end


def detect_gaps(
    words: list[WordTimestamp],
    wav_path: str | Path,
    config: CutsConfig,
    retake_ranges: list[tuple[float, float]] | None = None,
) -> list[Gap]:
    """Detect and classify inter-word gaps.

    Pipeline:
    1. Enumerate inter-word gaps from WhisperX word timestamps.
    2. Classify each gap using spectral flatness (breath vs silence vs noise).
       VAD is NOT used to filter gaps — on talking-head footage VAD marks everything
       as speech, causing 0 gaps to be detected.
    3. Mark gaps for cutting based on config thresholds.

    `retake_ranges` (start_s, end_s spans that a later pass cuts as retakes/outtakes)
    lets the confidence guards ignore words that won't survive to the output — those
    guards exist only to avoid clipping *kept* speech, so a doomed word must not block
    a cut. See `_build_gaps`.
    """
    wav_path = Path(wav_path)
    audio, sr = _load_audio(wav_path)

    # Compute peak amplitude once for the full track. Used for:
    # - relative breath amplitude ceiling (jumpcutter: breath must be << speech level)
    # - failure tolerance threshold (jumpcutter: allow small fraction of spikes in silence)
    peak_amplitude = float(np.max(np.abs(audio))) if len(audio) > 0 else 1.0

    gaps = _build_gaps(words, audio, sr, config, peak_amplitude, retake_ranges)
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


def _find_dominant_speech_span(
    audio: np.ndarray,
    sr: int,
    word_start: float,
    word_end: float,
    config: CutsConfig,
    min_silence_ms: float = 100.0,
) -> tuple[float, float]:
    """Find the speech run that actually carries an over-long word's audio.

    WhisperX stretches a word's timestamps across neighbouring silence, and it does so
    in both directions: sometimes the speech sits at the head of the span (a short
    function word followed by a long pause), sometimes at the tail (the word is pulled
    back to butt against the previous word, with the pause left in between). Splitting
    the span on sustained silence and taking the longest run finds the speech either
    way — clamping only the end deletes a tail-anchored word, because the real audio
    then falls inside the gap and gets cut.

    Returns (start, end) within [word_start, word_end], unchanged when no sustained
    silence splits the span (the word is genuinely long, e.g. a held vowel).
    """
    frame_size = max(64, int(0.010 * sr))  # 10ms frames
    required_frames = max(1, int(min_silence_ms / 10))
    silence_thresh = float(10 ** (config.silence_threshold_db / 20))

    start_sample = int(word_start * sr)
    end_sample = int(word_end * sr)

    runs: list[tuple[int, int]] = []  # [start, end) sample offsets of each speech run
    run_start: int | None = None
    first_silent_pos: int | None = None
    consecutive_silent = 0

    for pos in range(start_sample, end_sample, frame_size):
        frame = audio[pos : pos + frame_size]
        if len(frame) < 64:
            break
        fraction_above = float(np.mean(np.abs(frame) > silence_thresh))
        if fraction_above < config.failure_tolerance_ratio:
            if consecutive_silent == 0:
                first_silent_pos = pos
            consecutive_silent += 1
            if consecutive_silent >= required_frames and run_start is not None:
                runs.append((run_start, first_silent_pos))  # type: ignore[arg-type]
                run_start = None
        else:
            consecutive_silent = 0
            if run_start is None:
                run_start = pos
    if run_start is not None:
        runs.append((run_start, end_sample))

    if not runs:
        return word_start, word_end

    best = max(runs, key=lambda r: r[1] - r[0])
    return best[0] / sr, best[1] / sr


def _frame_levels_db(
    audio: np.ndarray, sr: int, start: float, end: float, frame_size: int
) -> list[tuple[float, float]]:
    """Per-frame (time, RMS dBFS) over [start, end), one entry per frame_size samples."""
    end_sample = min(int(end * sr), len(audio))
    return [
        (pos / sr, 20 * np.log10(float(np.sqrt(np.mean(audio[pos : pos + frame_size] ** 2))) + 1e-9))
        for pos in range(int(start * sr), end_sample - frame_size + 1, frame_size)
    ]


def _find_trailing_speech_end(
    audio: np.ndarray,
    sr: int,
    word_start: float,
    word_end: float,
    gap_end: float,
    config: CutsConfig,
    max_extend_ms: float = 800.0,
    max_closure_ms: float = 90.0,
    tail_margin_db: float = 25.0,
) -> float:
    """Scan forward from word_end to find where the word's trailing speech ends.

    WhisperX often truncates a word's end timestamp before quiet trailing consonants
    finish (sibilants/liquids: "MySQL"→/l/, "SSDs"→/z/). Because edl.py starts its cut
    at the word end, those tails get clipped. This walks forward past the truncated
    tail so the cut can start after the real speech end.

    A word can carry a whole trailing syllable past a *stop-closure* — the brief
    silence of a /d/,/t/,/k/… before a final sibilant (e.g. "SS-Dee-z"). WhisperX
    may cut the word at the closure, leaving the last syllable stranded in the gap.
    So we bridge silences up to `max_closure_ms` and stop at the first silence longer
    than that (a real pause — beyond it lies a breath or the next word, not this word).

    The budget applies **from the first frame**, not only once speech has been seen.
    WhisperX truncates a word *at* the closure as readily as after it, in which case the
    scan opens on silence and the stranded syllable sits just past it — "plugins.dat"
    aligned to `.dat` = 44.459–44.639s while the spoken "dat" ran 44.729–45.129s. Bailing
    out on that first silent frame handed the EDL the raw word end and the whole syllable
    was cut. Returns a time in [word_end, min(gap_end, word_end + max_extend)], and
    word_end unchanged when the silence outlasts the budget (accurate alignment — the
    common case), so the scan stays inert for aligned words.

    A frame counts as this word's speech only if it also stays within `tail_margin_db`
    of the word's own loudest frame. The absolute floor alone walks straight through an
    exhale — a breath clears `silence_threshold_db`, so the scan sailed to the far side
    of it and handed edl.py a speech_end at the next word's start, leaving no room for a
    cut: "...fixed half of that." kept its whole 600 ms exhale, and the gap was reported
    as an EDL floor decline rather than as this. A trailing consonant belongs to the
    word and stays near its level; a breath is tens of dB down.
    """
    frame_size = max(64, int(0.010 * sr))  # 10 ms frames
    silence_thresh = float(10 ** (config.silence_threshold_db / 20))
    closure_samples = max_closure_ms / 1000.0 * sr

    word_levels = _frame_levels_db(audio, sr, word_start, word_end, frame_size)
    tail_floor_db = (max(db for _, db in word_levels) - tail_margin_db) if word_levels else -np.inf

    start_sample = int(word_end * sr)
    limit = min(gap_end, word_end + max_extend_ms / 1000.0)
    end_sample = int(limit * sr)

    last_speech_end = float(word_end)  # end of the most recent speech frame
    silence_run = 0                    # consecutive silent samples since last speech

    for pos in range(start_sample, end_sample, frame_size):
        frame = audio[pos : pos + frame_size]
        if len(frame) < 64:
            break
        frame_db = 20 * np.log10(float(np.sqrt(np.mean(frame ** 2))) + 1e-9)
        is_speech = (
            float(np.mean(np.abs(frame) > silence_thresh)) >= config.failure_tolerance_ratio
            and frame_db > tail_floor_db
        )
        if is_speech:
            silence_run = 0
            last_speech_end = (pos + frame_size) / sr
        else:
            silence_run += frame_size
            if silence_run > closure_samples:
                break  # real pause — the trailing syllable ended at last_speech_end

    return min(last_speech_end, limit)


def _find_speech_onset_backward(
    audio: np.ndarray,
    sr: int,
    gap_start: float,
    word_start: float,
    config: CutsConfig,
    min_silence_ms: float = 100.0,
) -> float:
    """Scan backward from word_start for the last contiguous audible run before it.

    The mirror of `_find_trailing_speech_end`. That one exists because WhisperX truncates
    word *ends*, so the cut's left edge must be measured rather than taken from the
    timestamp. WhisperX mis-times word *starts* the same way — but the cut's right edge
    (`nxt.start - pad`) was still taken from the timestamp, so the only defence against a
    late start was to refuse the cut outright and leave the whole gap in.

    **This finds audible audio, not specifically the word.** It walks back through
    contiguous above-threshold frames from `word_start` and stops at the first silence of
    at least `min_silence_ms`. That run is the word's true onset when the word simply
    started before its timestamp — but it can equally be a breath, or untranscribed speech
    sitting in the gap. All three are things a cut should stop at, so the conservative
    reading is the useful one; do not read the result as "the word starts here".

    This is also why the caller applies it only where the timestamp is already distrusted.
    Used on every gap it would stop the pipeline removing untranscribed audio, which is
    deliberate behaviour, not a bug.

    Returns a time in [gap_start, word_start]; **never later than word_start**, so a cut
    derived from it is always a subset of the cut the raw timestamp would have produced.
    That one-sided guarantee is what makes it safe: it can shrink a cut, never extend one
    into a word. Returns word_start unchanged when the audio there is already silent
    (accurate alignment — the common case), so it is inert for well-aligned words.
    """
    frame_size = max(64, int(0.010 * sr))
    required_frames = max(1, int(min_silence_ms / 10))
    silence_thresh = float(10 ** (config.silence_threshold_db / 20))

    floor_sample = int(gap_start * sr)
    pos = int(word_start * sr)

    earliest_speech = pos
    silent_run = 0

    while pos - frame_size >= floor_sample:
        pos -= frame_size
        frame = audio[pos : pos + frame_size]
        if len(frame) < 64:
            break
        is_speech = float(np.mean(np.abs(frame) > silence_thresh)) >= config.failure_tolerance_ratio
        if is_speech:
            silent_run = 0
            earliest_speech = pos
        else:
            silent_run += 1
            if silent_run >= required_frames:
                break  # a real pause — the word's speech began at earliest_speech

    return min(earliest_speech / sr, word_start)


_LEAD_SPEECH_FRAMES = 3  # consecutive 10 ms frames of speech that end a lead-in run


def _find_leading_speech_start(
    audio: np.ndarray,
    sr: int,
    word_start: float,
    word_end: float,
    min_lead_ms: float = 150.0,
    max_lead_ms: float = 1000.0,
    lead_margin_db: float = 25.0,
) -> float:
    """Scan forward from word_start for the first frame of the word's real speech.

    The mirror of `_find_trailing_speech_end`. That one exists because WhisperX truncates
    word *ends*; this one because it also back-dates word *starts*, pulling them across
    the inhale in front of a sentence. The breath then sits inside the word's own span,
    where nothing can reach it: `_build_gaps` only measures between words[i].end and
    words[i+1].start, so the gap it sees stops short of the breath, and edl.py's cut ends
    a fixed pad before a timestamp that is itself hundreds of ms early. The breath plays
    ("...needs 21 bits." <breath> "The other half...", 600 ms of it).

    An inhale is not silence — it sits well above `silence_threshold_db`, so the
    speech/silence test the other scans use cannot see it. What separates it from speech
    is level *relative to this word*: that breath ran about -44 dB against the word's own
    -8 dB peak. So a lead-in qualifies only when it stays at least `lead_margin_db` below
    the word's loudest frame for `min_lead_ms` or more. A fricative onset fails one test
    or the other — /s/ is louder than that, and a soft one is far shorter.

    Returns a time in [word_start, word_start + max_lead_ms], never past word_end, and
    word_start unchanged when the word opens on speech (the common case), so the scan is
    inert for well-aligned words.
    """
    frame_size = max(64, int(0.010 * sr))
    levels = _frame_levels_db(audio, sr, word_start, word_end, frame_size)
    if len(levels) < _LEAD_SPEECH_FRAMES:
        return word_start

    threshold_db = max(db for _, db in levels) - lead_margin_db
    run = 0
    for t, db in levels:
        if t - word_start > max_lead_ms / 1000.0:
            break
        if db <= threshold_db:
            run = 0
            continue
        run += 1
        if run < _LEAD_SPEECH_FRAMES:
            continue
        # Back up to the first frame of this run — that is where speech actually starts.
        onset = t - (_LEAD_SPEECH_FRAMES - 1) * frame_size / sr
        return onset if onset - word_start >= min_lead_ms / 1000.0 else word_start

    return word_start

_LONG_WORD_DUR_S = 1.5  # words longer than this are suspect for alignment errors


def _in_retake(word: WordTimestamp, ranges: list[tuple[float, float]]) -> bool:
    """True if the word's midpoint falls inside any retake/outtake range.

    Midpoint (not overlap) so a word whose padded boundary grazes the range edge
    isn't misjudged; a word being cut as a retake sits squarely inside its range.
    """
    mid = (word.start + word.end) / 2
    return any(r_start <= mid <= r_end for r_start, r_end in ranges)


def _build_gaps(
    words: list[WordTimestamp],
    audio: np.ndarray,
    sr: int,
    config: CutsConfig,
    peak_amplitude: float,
    retake_ranges: list[tuple[float, float]] | None = None,
) -> list[Gap]:
    gaps: list[Gap] = []

    # Pre-pass: clamp words whose WhisperX-assigned duration is suspiciously long.
    # WhisperX sometimes stretches a short word's timestamps across the silence beside
    # it — forwards across a following pause, or backwards to butt against the previous
    # word. The inter-word gap is then only a few ms and is never cut, and when the
    # stretch runs backwards the word's real audio ends up inside the gap that does get
    # cut. Clamping to the dominant speech run restores a real gap on the correct side.
    for word in words[:-1]:
        if word.end - word.start > _LONG_WORD_DUR_S:
            true_start, true_end = _find_dominant_speech_span(audio, sr, word.start, word.end, config)
            if true_end < word.end - 0.050:  # at least 50ms of silence found
                word.end = true_end
            if true_start > word.start + 0.050:
                word.start = true_start

    # Pre-pass: pull a word's start off the inhale in front of it. WhisperX back-dates
    # word starts across the breath before a sentence, hiding the breath inside the
    # word's own span — the gap loop below only measures *between* words, so it never
    # sees it, and edl.py's fixed pad cannot reach it either. The cut then ends early
    # and the breath is audible before the sentence starts. Moving the start to the
    # real onset restores the gap, and the normal machinery removes it from there.
    for word in words:
        onset = _find_leading_speech_start(audio, sr, word.start, word.end)
        if onset > word.start:
            word.start = onset

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
        speech_end = _find_trailing_speech_end(audio, sr, words[i].start, raw_start, gap_end, config)

        duration_ms = (gap_end - effective_start) * 1000

        if duration_ms <= 0:
            continue

        gap_type = _classify_gap(audio, sr, effective_start, gap_end, duration_ms, config, peak_amplitude)

        prev_conf = words[i].confidence
        next_conf = words[i + 1].confidence

        # The confidence guards below protect kept speech from being clipped. A word
        # inside a retake range is slated for removal, so it is not speech to protect —
        # treat it as fully confident so it can't block a cut it will never be part of.
        # (Without this, silence in front of an aborted low-confidence take survives as
        # dead air, because the guard defends a word the retake pass then deletes.)
        # Only the preceding word needs this. A doomed *following* word no longer blocks
        # anything: its branch measures the onset from audio instead of vetoing.
        if retake_ranges and _in_retake(words[i], retake_ranges):
            prev_conf = 1.0

        clip_duration_s = len(audio) / sr
        skip_reason = ""
        # Default: trust the next word's timestamp as the cut's right edge. Only the
        # low-confidence branch below replaces it with an audio-measured onset.
        speech_onset = gap_end
        if config.preserve_start_s > 0 and effective_start < config.preserve_start_s:
            should_cut = False
            skip_reason = f"preserve_start ({effective_start:.3f}s < {config.preserve_start_s}s)"
        elif config.preserve_end_s > 0 and gap_end > clip_duration_s - config.preserve_end_s:
            should_cut = False
            skip_reason = f"preserve_end ({gap_end:.3f}s > clip-{config.preserve_end_s}s)"
        elif next_conf < config.min_word_confidence:
            # The word we're cutting INTO is uncertain, so its start timestamp cannot be
            # trusted as the cut's right edge. Measure the onset from the audio instead of
            # refusing the cut — the boundary then no longer depends on the timestamp, and
            # `speech_onset` is capped at the timestamp so the cut can only shrink.
            # (Refusing outright left the whole gap in: 1.8s of dead air in
            # ht-ghd-better-gitcli because the next word scored 0.33.)
            speech_onset = _find_speech_onset_backward(
                audio, sr, effective_start, gap_end, config
            )
            # Measuring the boundary is the whole fix here, so the duration rule must not
            # change with it: apply the same floor this gap's type would get below.
            floor_ms = config.min_breath_ms if gap_type == "breath" else config.min_silence_ms
            should_cut = duration_ms >= floor_ms
            if not should_cut:
                skip_reason = f"too short ({duration_ms:.0f}ms < {floor_ms}ms)"
            elif speech_onset - config.speech_pad_ms / 1000.0 <= speech_end:
                # The measured onset leaves no room between the previous word's speech end
                # and the pad, so edl.py declines the cut. Report it kept, so the flag
                # matches what the EDL actually does. (The same mismatch predates this
                # branch elsewhere in the chain and is deliberately left alone.)
                should_cut = False
                skip_reason = f"measured onset leaves nothing to cut ({speech_onset:.3f}s)"
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
            speech_onset=speech_onset,
            duration_ms=duration_ms,
            gap_type=gap_type,
            cut=should_cut,
            skip_reason=skip_reason,
        ))

    return gaps
