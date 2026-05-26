"""Debug report — single consolidated .debug.txt written after each pipeline run."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import ReelCutConfig
    from .edl import EDLEntry
    from .gap_detector import Gap
    from .transcriber import WordTimestamp


def write_debug_report(
    path: Path,
    *,
    clip_paths: list[str],
    config: "ReelCutConfig",
    raw_words: list["WordTimestamp"],
    aligned_words: list["WordTimestamp"],
    gaps_by_clip: dict[str, list["Gap"]],
    edl: list["EDLEntry"],
    caption_words: list["WordTimestamp"] | None,
    clip_info: list[dict],
    image_cues: list | None = None,
) -> None:
    """Write a single debug file covering every pipeline stage.

    clip_info entries: {clip, align_method, vad_method, hallucinations_dropped}
    caption_words: None when --dry-run (EDL built but no render).
    """
    from .edl import edl_summary

    out: list[str] = []
    _w = out.append

    _w("=== REELCUT DEBUG REPORT ===")
    _w(f"Generated : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    _w(f"Clips     : {', '.join(Path(c).name for c in clip_paths)}")
    _w("")

    # -------------------------------------------------------------------------
    # Config snapshot
    # -------------------------------------------------------------------------
    c = config
    _w("--- CONFIG ---")
    _w(f"  whisper : model={c.whisper.model}  beam_size={c.whisper.beam_size}"
       f"  language={c.whisper.language}  compute_type={c.whisper.compute_type}")
    _w(f"  cuts    : min_silence_ms={c.cuts.min_silence_ms}"
       f"  min_breath_ms={c.cuts.min_breath_ms}"
       f"  silence_threshold_db={c.cuts.silence_threshold_db}")
    _w(f"            vad_threshold={c.cuts.vad_threshold}"
       f"  breath_amplitude_ratio={c.cuts.breath_amplitude_ratio}"
       f"  failure_tolerance_ratio={c.cuts.failure_tolerance_ratio}")
    _w(f"            speech_pad_ms={c.cuts.speech_pad_ms}"
       f"  word_end_scan_ms={c.cuts.word_end_scan_ms}"
       f"  min_keep_ms={c.cuts.min_keep_ms}")
    _w("")

    # -------------------------------------------------------------------------
    # Pipeline summary (per clip)
    # -------------------------------------------------------------------------
    _w("--- PIPELINE SUMMARY ---")
    for info in clip_info:
        dropped = info["hallucinations_dropped"]
        drop_note = f"  [{dropped} hallucinated words dropped]" if dropped else ""
        _w(f"  {Path(info['clip']).name}")
        _w(f"    Alignment  : {info['align_method']}")
        _w(f"    VAD filter : {info['vad_method']}{drop_note}")
    _w("")

    # -------------------------------------------------------------------------
    # Stage 1 — raw Whisper output
    # -------------------------------------------------------------------------
    _w("--- STAGE 1: RAW WHISPER OUTPUT ---")
    _w(f"  ({len(raw_words)} words total)")
    for w in raw_words:
        _w(f"  {_ts(w.start):>9} → {_ts(w.end):<9}  {w.word!r:<30}  conf={w.confidence:.2f}"
           f"  clip={Path(w.clip_path).name}")
    _w("")

    # -------------------------------------------------------------------------
    # Stage 2 — after WhisperX alignment + VAD/energy filter
    # -------------------------------------------------------------------------
    total_dropped = sum(i["hallucinations_dropped"] for i in clip_info)
    _w("--- STAGE 2: AFTER ALIGNMENT + VAD FILTER ---")
    _w(f"  ({len(aligned_words)} words kept, {total_dropped} dropped as hallucinations)")
    for w in aligned_words:
        keep_flag = ""
        if not w.keep:
            keep_flag = "  [OUTTAKE]"
        _w(f"  {_ts(w.start):>9} → {_ts(w.end):<9}  {w.word!r:<30}  conf={w.confidence:.2f}{keep_flag}")
    _w("")

    # -------------------------------------------------------------------------
    # Stage 3 — final output captions (remapped timeline)
    # -------------------------------------------------------------------------
    _w("--- STAGE 3: OUTPUT CAPTIONS (final video timeline) ---")
    if caption_words:
        _w(f"  ({len(caption_words)} words in output video)")
        for w in caption_words:
            _w(f"  {_ts(w.start):>9} → {_ts(w.end):<9}  {w.word!r}")
    else:
        _w("  (not available — dry-run mode)")
    _w("")

    # -------------------------------------------------------------------------
    # Timeline — words and gaps interleaved in source-clip time
    # -------------------------------------------------------------------------
    _w("--- TIMELINE: WORDS + GAPS (source clip time) ---")
    for clip_path in clip_paths:
        clip_words = sorted(
            [w for w in aligned_words if w.clip_path == str(clip_path)],
            key=lambda w: w.start,
        )
        clip_gaps = gaps_by_clip.get(str(clip_path), [])
        gap_map = {(round(g.start, 4), round(g.end, 4)): g for g in clip_gaps}

        _w(f"\n  Clip: {Path(clip_path).name}  ({len(clip_words)} words, {len(clip_gaps)} gaps)")
        _w(f"  {'TIME RANGE':<21}  {'TYPE':<10}  {'CONTENT':<38}  DECISION")
        _w(f"  {'─'*21}  {'─'*10}  {'─'*38}  {'─'*8}")

        for i, w in enumerate(clip_words):
            keep_str = "KEEP" if w.keep else "CUT "
            content = f"{w.word!r:<28}  conf={w.confidence:.2f}"
            # Flag very short words that precede a cut — WhisperX sometimes assigns
            # < 50 ms windows to sub-tokens, making them acoustically inaudible.
            short_note = ""
            word_dur_ms = (w.end - w.start) * 1000
            if w.keep and word_dur_ms < 50 and i + 1 < len(clip_words):
                nxt_w = clip_words[i + 1]
                chk_gap = gap_map.get((round(w.end, 4), round(nxt_w.start, 4)))
                if chk_gap and chk_gap.cut:
                    short_note = f"  [!SHORT {word_dur_ms:.0f}ms — may be inaudible]"
            _w(f"  {_ts(w.start):>9}→{_ts(w.end):<10}  {'WORD':<10}  {content:<38}  {keep_str}{short_note}")

            if i < len(clip_words) - 1:
                nxt = clip_words[i + 1]
                gap = gap_map.get((round(w.end, 4), round(nxt.start, 4)))
                if gap:
                    cut_str = "CUT " if gap.cut else "KEEP"
                    eff_note = (
                        f"  eff={_ts(gap.effective_start)}"
                        if abs(gap.effective_start - gap.start) > 0.005
                        else ""
                    )
                    g_content = f"{gap.gap_type.upper()}: {gap.duration_ms:.0f}ms{eff_note}"
                    _w(f"  {_ts(gap.effective_start):>9}→{_ts(gap.end):<10}  {gap.gap_type.upper():<10}  {g_content:<38}  {cut_str}")
                elif nxt.start - w.end > 0.010:
                    dur_ms = (nxt.start - w.end) * 1000
                    _w(f"  {_ts(w.end):>9}→{_ts(nxt.start):<10}  {'(no gap)':<10}  {dur_ms:.0f}ms (below threshold)")
    _w("")

    # -------------------------------------------------------------------------
    # Image overlays
    # -------------------------------------------------------------------------
    _w("--- IMAGE OVERLAYS ---")
    if not config.images.enabled:
        _w("  (disabled)")
    elif image_cues is None:
        _w("  (not available — dry-run mode)")
    elif not image_cues:
        _w("  0 logos matched (no transcript words matched any gilbarbara/logos shortname)")
    else:
        _w(f"  {len(image_cues)} logo(s) detected")
        _w(f"  {'KEYWORD':<20}  {'OUTPUT TIME':<22}  FILE")
        _w(f"  {'─'*20}  {'─'*22}  {'─'*40}")
        for cue in image_cues:
            time_range = f"{_ts(cue.start)} → {_ts(cue.end)}"
            _w(f"  {cue.keyword:<20}  {time_range:<22}  {cue.image_path}")
    _w("")

    # -------------------------------------------------------------------------
    # EDL summary + full entry list
    # -------------------------------------------------------------------------
    summary = edl_summary(edl)
    _w("--- EDL SUMMARY ---")
    _w(f"  Keep : {summary['total_keep_s']}s  ({summary['keep_segments']} segments)")
    cut_breakdown = "  ".join(
        f"{r}×{n}" for r, n in summary["reasons"].items() if n > 0
    )
    _w(f"  Cut  : {summary['total_cut_s']}s  — {cut_breakdown or 'none'}")
    _w("")

    _w("--- EDL ENTRIES ---")
    _w(f"  {'#':>4}  {'TIME RANGE':<21}  {'CLIP':<22}  {'KEEP':<5}  {'DUR':>7}  REASON")
    _w(f"  {'─'*4}  {'─'*21}  {'─'*22}  {'─'*5}  {'─'*7}  {'─'*10}")
    for i, entry in enumerate(edl):
        keep_str = "KEEP " if entry.keep else "CUT  "
        dur = entry.end - entry.start
        clip_name = Path(entry.source_clip).name
        _w(
            f"  {i:>4}  {_ts(entry.start):>9}→{_ts(entry.end):<10}  {clip_name:<22}"
            f"  {keep_str}  {dur:>6.3f}s  {entry.reason}"
        )

    Path(path).write_text("\n".join(out) + "\n")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ts(t: float) -> str:
    """Format seconds as M:SS.mmm or SS.mmms."""
    if t >= 60:
        m = int(t // 60)
        s = t % 60
        return f"{m}:{s:06.3f}"
    return f"{t:.3f}s"
