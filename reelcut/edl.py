"""EDL generator — JSON edit decision list with sentence-boundary snapping."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from .gap_detector import Gap
from .transcriber import WordTimestamp, is_sentence_boundary

SegmentReason = Literal["speech", "silence", "breath", "noise", "outtake", "retake"]


@dataclass
class EDLEntry:
    start: float           # seconds, in source clip
    end: float             # seconds, in source clip
    keep: bool
    source_clip: str       # path to source video/wav file
    reason: SegmentReason


def generate_scriptless_edl(
    words: list[WordTimestamp],
    gaps: list[Gap],
    min_keep_ms: int = 50,
    speech_pad_ms: int = 30,
    mid_sentence_cut_floor_ms: int = 3000,
    sentence_pause_s: float = 0.4,
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
                is_sentence_boundary(curr.word, nxt.word, nxt.start - curr.end,
                                     pause_threshold_s=sentence_pause_s, include_clause=True)
                or gap.duration_ms >= mid_sentence_cut_floor_ms
            ):
                cut_start = gap.start                    # raw word end — never inside the word
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
) -> tuple[list[EDLEntry], list[EDLEntry]]:
    """Split EDL keep-entries at retake boundaries and mark retake regions as cuts.

    Args:
        entries: Existing EDL entry list.
        retake_ranges: Mapping of source_clip path → list of (start_s, end_s)
            time ranges that should be cut as retakes.
        words: If provided, words inside retake ranges are marked keep=False.

    Returns:
        (entries, wordless_drops) — updated EDL and any keep fragments that were
        dropped because they contained no aligned words (VAD false-positives at
        retake boundaries).
    """
    if not retake_ranges:
        return entries, []

    # Build a per-clip set of word start times for the wordless-keep filter below.
    word_starts_by_clip: dict[str, list[float]] = {}
    if words is not None:
        for w in words:
            if not w.keep:
                continue
            for r_start, r_end in retake_ranges.get(w.clip_path, []):
                if r_start <= w.start < r_end:
                    w.keep = False
                    break
        for w in words:
            word_starts_by_clip.setdefault(w.clip_path, []).append(w.start)

    def _has_word(clip: str, seg_start: float, seg_end: float) -> bool:
        return any(seg_start <= t < seg_end for t in word_starts_by_clip.get(clip, []))

    result: list[EDLEntry] = []
    wordless_drops: list[EDLEntry] = []
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
            # Drop keep fragments with no aligned words — these are VAD false-positives
            # (e.g. a breath tail) left between a gap cut and the retake boundary.
            if keep and words is not None and not _has_word(entry.source_clip, seg_start, seg_end):
                wordless_drops.append(EDLEntry(
                    start=seg_start, end=seg_end, keep=True,
                    source_clip=entry.source_clip, reason="speech",
                ))
                keep = False
            result.append(EDLEntry(
                start=seg_start,
                end=seg_end,
                keep=keep,
                source_clip=entry.source_clip,
                reason="speech" if keep else "retake",
            ))

    result.sort(key=lambda e: (e.source_clip, e.start))
    return result, wordless_drops


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

