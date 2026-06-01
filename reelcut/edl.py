"""EDL generator — JSON edit decision list with sentence-boundary snapping."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from .gap_detector import Gap
from .script_aligner import AlignedSegment
from .transcriber import WordTimestamp

SegmentReason = Literal["speech", "silence", "breath", "noise", "outtake", "retake"]


@dataclass
class EDLEntry:
    start: float           # seconds, in source clip
    end: float             # seconds, in source clip
    keep: bool
    source_clip: str       # path to source video/wav file
    reason: SegmentReason


def generate_edl(
    segments: list[AlignedSegment],
    gaps: list[Gap],
    words: list[WordTimestamp],
    min_keep_ms: int = 100,
) -> list[EDLEntry]:
    """Build an EDL from aligned segments and detected gaps.

    - All words inside an AlignedSegment are kept.
    - Gaps marked cut=True become cut entries.
    - Words not in any segment (outtakes) become cut entries.
    - Cut points snap to word boundaries (never mid-word).
    - Keep segments shorter than min_keep_ms are dropped and surrounding cuts merged.
    """
    if not words:
        return []

    # Mark words: kept if they appear in an aligned segment, outtake otherwise.
    # seg.words are slices of the original words list (same objects), so identity
    # comparison is reliable and avoids floating-point timestamp edge cases.
    segment_word_ids = {id(w) for seg in segments for w in seg.words}
    for w in words:
        w.keep = id(w) in segment_word_ids

    entries: list[EDLEntry] = []

    # Index words by clip for accurate snapping
    words_by_clip: dict[str, list[WordTimestamp]] = {}
    for w in words:
        words_by_clip.setdefault(w.clip_path, []).append(w)

    # Collect all keep intervals from aligned segments
    keep_intervals: list[tuple[float, float, str]] = []
    for seg in segments:
        if not seg.words:
            continue
        clip_words = words_by_clip.get(seg.clip_path, words)
        start = _snap_to_sentence_start(seg.words[0].start, clip_words)
        end = _snap_to_sentence_end(seg.words[-1].end, clip_words)
        # If the last word of this segment is shorter than min_keep_ms, extend the
        # interval end so the word has at least min_keep_ms ms of audio context.
        # WhisperX can assign very narrow windows to sub-tokens of compound words
        # (e.g. "-2026" in "CVE-2026-31431"), making them acoustically inaudible.
        last_word = seg.words[-1]
        if (last_word.end - last_word.start) * 1000 < min_keep_ms:
            end = max(end, last_word.start + min_keep_ms / 1000.0)
        keep_intervals.append((start, end, seg.clip_path))

    # Merge overlapping/adjacent keep intervals (same clip)
    keep_intervals = _merge_intervals(keep_intervals)

    # Build a timeline: walk from clip start to end, emitting keep/cut entries
    if not keep_intervals:
        return []

    clip_groups = _group_by_clip(keep_intervals)

    for clip_path, intervals in clip_groups.items():
        clip_words = [w for w in words if w.clip_path == clip_path]
        if not clip_words:
            continue

        timeline_start = clip_words[0].start
        timeline_end = clip_words[-1].end

        cursor = timeline_start
        for seg_start, seg_end in sorted(intervals):
            if cursor < seg_start:
                # Gap before this keep segment — determine reason
                gap_reason = _gap_reason_for_range(cursor, seg_start, gaps)
                entries.append(EDLEntry(
                    start=cursor,
                    end=seg_start,
                    keep=False,
                    source_clip=clip_path,
                    reason=gap_reason,
                ))
            entries.append(EDLEntry(
                start=seg_start,
                end=seg_end,
                keep=True,
                source_clip=clip_path,
                reason="speech",
            ))
            cursor = seg_end

        # Trailing gap after last keep segment
        if cursor < timeline_end:
            entries.append(EDLEntry(
                start=cursor,
                end=timeline_end,
                keep=False,
                source_clip=clip_path,
                reason="outtake",
            ))

    return _optimize_edl(entries, min_keep_ms)


def generate_scriptless_edl(
    words: list[WordTimestamp],
    gaps: list[Gap],
    min_keep_ms: int = 50,
    speech_pad_ms: int = 30,
    mid_sentence_cut_floor_ms: int = 3000,
) -> list[EDLEntry]:
    """Build an EDL with no script: keep all speech, cut at every marked gap.

    Cut boundaries are placed at:
      - gap.effective_start  (true silence onset — may be before Whisper's word end)
      - nxt.start - pad_s    (leave a safety margin before the next word starts)

    This prevents clipping word edges when Whisper timestamps are off by ±30 ms.

    mid_sentence_cut_floor_ms: gaps below this duration are not cut unless the
    preceding word ends with sentence-ending punctuation. Prevents jarring jump
    cuts landing in the middle of a phrase (e.g. mid-sentence restarts).
    """
    if not words:
        return []

    # All words are kept in scriptless mode — only silence between them is cut.
    for w in words:
        w.keep = True

    pad_s = speech_pad_ms / 1000.0

    # Keyed by original word boundary (words[i].end, words[i+1].start) for fast lookup
    gap_map: dict[tuple[float, float], Gap] = {}
    for g in gaps:
        gap_map[(round(g.start, 4), round(g.end, 4))] = g

    entries: list[EDLEntry] = []
    words_by_clip: dict[str, list[WordTimestamp]] = {}
    for w in words:
        words_by_clip.setdefault(w.clip_path, []).append(w)

    for clip_path, clip_words in words_by_clip.items():
        clip_words = sorted(clip_words, key=lambda w: w.start)
        seg_start = clip_words[0].start
        seg_end = clip_words[0].end

        for i in range(len(clip_words) - 1):
            curr = clip_words[i]
            nxt = clip_words[i + 1]
            gap = gap_map.get((round(curr.end, 4), round(nxt.start, 4)))

            if gap and gap.cut and (
                _is_sentence_end(curr) or gap.duration_ms >= mid_sentence_cut_floor_ms
            ):
                cut_start = gap.effective_start          # true silence onset
                cut_end   = nxt.start - pad_s            # keep natural lead before next word

                # If the word immediately before this cut is shorter than min_keep_ms,
                # push cut_start forward so the word has a minimum audible window.
                # WhisperX can assign < 50 ms to sub-tokens of compound words (e.g.
                # "-2026" in "CVE-2026-31431"), making them inaudible even when kept.
                curr_dur_ms = (curr.end - curr.start) * 1000
                if curr_dur_ms < min_keep_ms:
                    extended = curr.start + min_keep_ms / 1000.0
                    cut_start = min(extended, cut_end - 0.010)

                if cut_end > cut_start + 0.010:          # only cut if ≥10 ms remains
                    entries.append(EDLEntry(
                        start=seg_start, end=cut_start, keep=True,
                        source_clip=clip_path, reason="speech",
                    ))
                    entries.append(EDLEntry(
                        start=cut_start, end=cut_end, keep=False,
                        source_clip=clip_path, reason=gap.gap_type,  # type: ignore[arg-type]
                    ))
                    seg_start = cut_end
            seg_end = nxt.end

        entries.append(EDLEntry(
            start=seg_start, end=seg_end, keep=True,
            source_clip=clip_path, reason="speech",
        ))

    return _optimize_edl(entries, min_keep_ms)


def apply_retake_cuts(
    entries: list[EDLEntry],
    retake_ranges: dict[str, list[tuple[float, float]]],
    words: list[WordTimestamp] | None = None,
) -> list[EDLEntry]:
    """Split EDL keep-entries at retake boundaries and mark retake regions as cuts.

    Args:
        entries: Existing EDL entry list.
        retake_ranges: Mapping of source_clip path → list of (start_s, end_s)
            time ranges that should be cut as retakes.
        words: If provided, words inside retake ranges are marked keep=False.

    Returns:
        New EDL entry list with retake regions marked as cut (reason="retake"),
        sorted by clip and start time.
    """
    if not retake_ranges:
        return entries

    if words is not None:
        for w in words:
            if not w.keep:
                continue
            for r_start, r_end in retake_ranges.get(w.clip_path, []):
                if r_start <= w.start < r_end:
                    w.keep = False
                    break

    result: list[EDLEntry] = []
    for entry in entries:
        clip_cuts = retake_ranges.get(entry.source_clip, [])
        if not entry.keep or not clip_cuts:
            result.append(entry)
            continue

        # Walk through the keep entry, splitting around any overlapping retake ranges.
        # pending tracks (seg_start, seg_end, is_keep) sub-segments still to resolve.
        pending: list[tuple[float, float, bool]] = [(entry.start, entry.end, True)]
        for r_start, r_end in sorted(clip_cuts):
            next_pending: list[tuple[float, float, bool]] = []
            for seg_start, seg_end, keep in pending:
                if not keep or r_end <= seg_start or r_start >= seg_end:
                    next_pending.append((seg_start, seg_end, keep))
                    continue
                # Retake overlaps this keep sub-segment — split it
                if seg_start < r_start:
                    next_pending.append((seg_start, r_start, True))
                next_pending.append((max(seg_start, r_start), min(seg_end, r_end), False))
                if r_end < seg_end:
                    next_pending.append((r_end, seg_end, True))
            pending = next_pending

        for seg_start, seg_end, keep in pending:
            result.append(EDLEntry(
                start=seg_start,
                end=seg_end,
                keep=keep,
                source_clip=entry.source_clip,
                reason="speech" if keep else "retake",
            ))

    result.sort(key=lambda e: (e.source_clip, e.start))
    return result


def save_edl(entries: list[EDLEntry], path: str | Path) -> Path:
    """Serialize EDL to a human-readable JSON file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = [asdict(e) for e in entries]
    path.write_text(json.dumps(data, indent=2))
    return path


def load_edl(path: str | Path) -> list[EDLEntry]:
    """Deserialize EDL from a JSON file."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"EDL file not found: {path}")
    data = json.loads(path.read_text())
    return [EDLEntry(**entry) for entry in data]


def edl_summary(entries: list[EDLEntry]) -> dict:
    """Return a summary dict: total_keep_s, total_cut_s, segment counts."""
    keep = [e for e in entries if e.keep]
    cut = [e for e in entries if not e.keep]
    return {
        "keep_segments": len(keep),
        "cut_segments": len(cut),
        "total_keep_s": round(sum(e.end - e.start for e in keep), 3),
        "total_cut_s": round(sum(e.end - e.start for e in cut), 3),
        "reasons": {r: sum(1 for e in cut if e.reason == r) for r in ("silence", "breath", "noise", "outtake", "retake")},
    }


# ---------------------------------------------------------------------------
# EDL optimisation (unsilence + jumpcutter patterns)
# ---------------------------------------------------------------------------

def _optimize_edl(entries: list[EDLEntry], min_keep_ms: int) -> list[EDLEntry]:
    """Two-pass cleanup after the raw EDL is built.

    Pass 1 — drop short keep segments (jumpcutter min_loud_part_duration):
      Any keep entry whose duration is below min_keep_ms is converted to a cut.
      These are sub-word fragments that survived gap detection — isolated clicks,
      partial phonemes, or rounding artifacts that produce spurious FFmpeg calls.

    Pass 2 — merge adjacent cuts (unsilence combine_intervals):
      After pass 1, consecutive cut entries on the same clip are collapsed into
      one. This reduces EDL fragmentation: fewer cut entries means fewer keep
      segments, which means fewer FFmpeg subprocess invocations in the renderer.
    """
    if not entries or min_keep_ms <= 0:
        return entries

    # Pass 1: convert short keeps to cuts
    result: list[EDLEntry] = []
    for entry in entries:
        if entry.keep and (entry.end - entry.start) * 1000 < min_keep_ms:
            result.append(EDLEntry(
                start=entry.start,
                end=entry.end,
                keep=False,
                source_clip=entry.source_clip,
                reason="noise",
            ))
        else:
            result.append(entry)

    # Pass 2: merge adjacent cuts on the same clip
    merged: list[EDLEntry] = [result[0]]
    for entry in result[1:]:
        prev = merged[-1]
        if (
            not entry.keep
            and not prev.keep
            and entry.source_clip == prev.source_clip
            and entry.start <= prev.end + 0.001
        ):
            merged[-1] = EDLEntry(
                start=prev.start,
                end=entry.end,
                keep=False,
                source_clip=prev.source_clip,
                reason=prev.reason,
            )
        else:
            merged.append(entry)

    return merged


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SENTENCE_END_CHARS = frozenset(".!?,;:")


def _is_sentence_end(word: WordTimestamp) -> bool:
    return bool(word.word) and word.word[-1] in _SENTENCE_END_CHARS


def _snap_to_sentence_end(t: float, words: list[WordTimestamp], window: float = 0.6) -> float:
    """Snap end cut to the nearest sentence-ending word within `window` seconds.

    Prefers words ending in . ! ? , ; : so cuts land after natural pauses.
    Falls back to the nearest word end within the window; returns t unchanged
    if no word is found within the window (avoids snapping to unrelated segments).
    """
    if not words:
        return t
    candidates = [w for w in words if w.end >= t and w.end <= t + window and _is_sentence_end(w)]
    if candidates:
        return min(candidates, key=lambda w: abs(w.end - t)).end
    # fallback: nearest word end within window only (don't snap to distant words)
    window_words = [w for w in words if t <= w.end <= t + window]
    if window_words:
        return min(window_words, key=lambda w: abs(w.end - t)).end
    return t


def _snap_to_sentence_start(t: float, words: list[WordTimestamp], window: float = 0.6) -> float:
    """Snap start cut to the word that begins a sentence within `window` seconds before t.

    A sentence start is the word immediately after a sentence-ending word.
    Falls back to the nearest word start within the window; returns t unchanged
    if no word is found within the window (avoids snapping to unrelated segments).
    """
    if not words:
        return t
    sorted_words = sorted(words, key=lambda w: w.start)
    # Find words that follow a sentence-ending word and are within the window
    candidates = []
    for i, w in enumerate(sorted_words):
        if w.start < t - window or w.start > t:
            continue
        if i == 0 or _is_sentence_end(sorted_words[i - 1]):
            candidates.append(w)
    if candidates:
        return min(candidates, key=lambda w: abs(w.start - t)).start
    # fallback: nearest word start within window only (don't snap to distant words)
    window_words = [w for w in sorted_words if t - window <= w.start <= t]
    if window_words:
        return min(window_words, key=lambda w: abs(w.start - t)).start
    return t


def _merge_intervals(
    intervals: list[tuple[float, float, str]],
) -> list[tuple[float, float, str]]:
    """Merge overlapping/adjacent intervals that share the same clip path."""
    if not intervals:
        return []
    intervals = sorted(intervals, key=lambda x: (x[2], x[0]))
    merged = [intervals[0]]
    for start, end, clip in intervals[1:]:
        prev_start, prev_end, prev_clip = merged[-1]
        if clip == prev_clip and start <= prev_end + 0.001:
            merged[-1] = (prev_start, max(prev_end, end), clip)
        else:
            merged.append((start, end, clip))
    return merged


def _group_by_clip(
    intervals: list[tuple[float, float, str]],
) -> dict[str, list[tuple[float, float]]]:
    result: dict[str, list[tuple[float, float]]] = {}
    for start, end, clip in intervals:
        result.setdefault(clip, []).append((start, end))
    return result


def _gap_reason_for_range(
    start: float,
    end: float,
    gaps: list[Gap],
) -> SegmentReason:
    """Find the dominant gap type for a time range."""
    overlapping = [
        g for g in gaps
        if g.start < end and g.end > start
    ]
    if not overlapping:
        return "outtake"
    # Pick the type of the longest overlapping gap
    dominant = max(overlapping, key=lambda g: g.duration_ms)
    return dominant.gap_type  # type: ignore[return-value]
