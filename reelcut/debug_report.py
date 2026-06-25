"""Debug report — split .debug.* files written after each pipeline run."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import ReelCutConfig
    from .edl import EDLEntry
    from .gap_detector import Gap
    from .retake_detector import RetakeCandidate
    from .transcriber import WordTimestamp


def write_debug_report(
    base_path: Path,
    *,
    clip_paths: list[str],
    config: "ReelCutConfig",
    raw_words: list["WordTimestamp"],
    post_align_words: list["WordTimestamp"] | None = None,
    align_segments: list[dict] | None = None,
    post_retrans_words: list["WordTimestamp"] | None = None,
    aligned_words: list["WordTimestamp"],
    gaps_by_clip: dict[str, list["Gap"]],
    edl: list["EDLEntry"],
    caption_words: list["WordTimestamp"] | None,
    clip_info: list[dict],
    retrans_log: list[dict] | None = None,
    retake_ranges: dict[str, list[tuple[float, float]]] | None = None,
    retake_candidates: dict[str, list["RetakeCandidate"]] | None = None,
    wordless_drops: list["EDLEntry"] | None = None,
    image_cues: list | None = None,
) -> None:
    """Write split debug files: .debug.1.raw.txt, .debug.2.post-retrans.txt, .debug.3.post-align.txt, .debug.4.post-vad.txt, .debug.5.timeline.txt, .debug.6.summary.txt."""
    from .edl import edl_summary

    header = (
        f"=== REELCUT DEBUG REPORT ===\n"
        f"Generated : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"Clips     : {', '.join(Path(c).name for c in clip_paths)}\n"
    )

    # -------------------------------------------------------------------------
    # summary — config, pipeline summary, retrans windows, retake detection,
    #           image overlays, EDL summary + entries
    # -------------------------------------------------------------------------
    s: list[str] = [header]
    _s = s.append

    c = config
    _s("--- CONFIG ---")
    _s(f"  whisper : model={c.whisper.model}  beam_size={c.whisper.beam_size}"
       f"  language={c.whisper.language}  compute_type={c.whisper.compute_type}")
    _s(f"            no_speech_threshold={c.whisper.no_speech_threshold}"
       f"  retranscribe_no_speech_threshold={c.whisper.retranscribe_no_speech_threshold}"
       f"  min_alignment_confidence={c.whisper.min_alignment_confidence}")
    _s(f"            wide_word_threshold_s={c.whisper.wide_word_threshold_s}"
       f"  retranscribe_low_conf_gap_ms={c.whisper.retranscribe_low_conf_gap_ms}"
       f"  retranscribe_large_gap_ms={c.whisper.retranscribe_large_gap_ms}"
       f"  retranscribe_merge_gap_s={c.whisper.retranscribe_merge_gap_s}")
    _s(f"  cuts    : min_silence_ms={c.cuts.min_silence_ms}"
       f"  min_breath_ms={c.cuts.min_breath_ms}"
       f"  silence_threshold_db={c.cuts.silence_threshold_db}")
    _s(f"            vad_threshold={c.cuts.vad_threshold}"
       f"  min_word_confidence={c.cuts.min_word_confidence}"
       f"  low_confidence_threshold={c.cuts.low_confidence_threshold}")
    _s(f"            low_confidence_min_gap_ms={c.cuts.low_confidence_min_gap_ms}"
       f"  mid_sentence_cut_floor_ms={c.cuts.mid_sentence_cut_floor_ms}"
       f"  min_keep_ms={c.cuts.min_keep_ms}")
    _s(f"            speech_pad_ms={c.cuts.speech_pad_ms}"
       f"  word_end_scan_ms={c.cuts.word_end_scan_ms}")
    _s(f"            preserve_start_s={c.cuts.preserve_start_s}"
       f"  preserve_end_s={c.cuts.preserve_end_s}")
    rep = (f"ON  min_retake_words={c.cuts.min_retake_words}"
           f"  max_retake_gap_s={c.cuts.max_retake_gap_s}"
           f"  min_match_ratio={c.cuts.min_match_ratio}"
           f"  min_reword_overlap={c.cuts.min_reword_overlap}"
           if c.cuts.repetition_detection else "OFF")
    _s(f"  retakes : {rep}")
    _s("")

    _s("--- PIPELINE SUMMARY ---")
    for info in clip_info:
        dropped = info["hallucinations_dropped"]
        drop_note = f"  [{dropped} hallucinated words dropped]" if dropped else ""
        _s(f"  {Path(info['clip']).name}")
        _s(f"    Alignment  : {info['align_method']}")
        _s(f"    VAD filter : {info['vad_method']}{drop_note}")
    _s("")

    _s("--- RETRANSCRIPTION WINDOWS ---")
    if not retrans_log:
        _s("  (none — no suspicious windows detected)")
    else:
        n_expanded   = sum(1 for e in retrans_log if e.get("pre_exp_start", e["win_start"]) != e["win_start"] or e.get("pre_exp_end", e["win_end"]) != e["win_end"])
        n_hard_capped = sum(1 for e in retrans_log if e.get("hard_capped"))
        _s(f"  {len(retrans_log)} window(s)  |  {n_expanded} expanded to sentence boundary  |  {n_hard_capped} hit 20s hard cap")
        _s("")
        for entry in sorted(retrans_log, key=lambda e: e["win_start"]):
            win_s = _ts(entry["win_start"])
            win_e = _ts(entry["win_end"])
            dur = entry["win_end"] - entry["win_start"]
            cap_flag = "  [⚠ HARD CAP — sentence exceeded 20s]" if entry.get("hard_capped") else ""
            _s(f"  [{win_s} → {win_e}]  trigger={entry['label']}  dur={dur:.3f}s"
               f"  action={entry['action']}{cap_flag}")
            pre_s = entry.get("pre_exp_start", entry["win_start"])
            pre_e = entry.get("pre_exp_end",   entry["win_end"])
            if pre_s != entry["win_start"] or pre_e != entry["win_end"]:
                _s(f"    expanded from  : [{_ts(pre_s)} → {_ts(pre_e)}]  dur={pre_e - pre_s:.3f}s  → sentence boundary")
            replaced = entry["before"]
            if replaced:
                replaced_str = "  ".join(f"{w.word!r}({w.confidence:.2f})" for w in replaced)
                _s(f"    before   : {replaced_str}")
            else:
                _s(f"    before   : (window was empty — gap insertion)")
            raw = entry["found_raw"]
            sub_clips = entry.get("sub_clips", [])
            if raw:
                raw_str = "  ".join(f"{w.word!r}({w.confidence:.2f})" for w in raw)
                _s(f"    raw      : {raw_str}")
            else:
                _s(f"    raw      : (nothing transcribed)")
            if len(sub_clips) > 1:
                for sc_i, sc in enumerate(sub_clips):
                    abs_start = entry["win_start"] + sc["start_s"]
                    abs_end   = entry["win_start"] + sc["end_s"]
                    if sc["words"]:
                        sc_str = "  ".join(f"{w.word!r}({w.confidence:.2f})" for w in sc["words"])
                    else:
                        sc_str = "(nothing)"
                    _s(f"    sub[{sc_i}]  [{_ts(abs_start)} → {_ts(abs_end)}]: {sc_str}")
            kept = entry["found_kept"]
            dropped = entry["found_dropped"]
            if kept:
                kept_str = "  ".join(f"{w.word!r}({w.confidence:.2f})" for w in kept)
                _s(f"    kept     : {kept_str}")
            rescued = entry.get("found_rescued", [])
            if rescued:
                resc_str = "  ".join(f"{w.word!r}({w.confidence:.2f})" for w in rescued)
                _s(f"    rescued  : {resc_str}  [below conf but matched confident original — kept]")
            if dropped:
                drop_str = "  ".join(f"{w.word!r}({w.confidence:.2f})" for w in dropped)
                _s(f"    dropped  : {drop_str}  [below conf threshold]")
    _s("")

    _s("--- RETAKE DETECTION ---")
    if not config.cuts.repetition_detection:
        _s("  (disabled — set repetition_detection: true to enable)")
    elif not retake_candidates:
        _s("  (enabled — no repeated phrases found)")
    else:
        all_candidates = [c for v in retake_candidates.values() for c in v]
        n_kept = sum(1 for c in all_candidates if c.kept)
        n_skipped = len(all_candidates) - n_kept
        total_s = sum(e - s for v in (retake_ranges or {}).values() for s, e in v)
        _s(f"  {len(all_candidates)} candidate(s) evaluated  |  {n_kept} cut ({total_s:.1f}s)  |  {n_skipped} skipped")
        _s(f"  min_match_ratio={config.cuts.min_match_ratio}")
        for clip, cands in retake_candidates.items():
            _s(f"  {Path(clip).name}")
            for c in cands:
                phrase = " ".join(c.ngram)
                mark = "CUT " if c.kept else "SKIP"
                _s(f"    {'✓' if c.kept else '✗'} {mark}  {_ts(c.cut_start_s)} → {_ts(c.cut_end_s)}"
                   f"  ({c.cut_end_s - c.cut_start_s:.3f}s)")
                detail = f"match \"{phrase}\" … {c.match_len} words matched / {c.cut_len}-word cut  ratio={c.ratio:.2f}"
                if c.skip_reason:
                    detail += f"  ({c.skip_reason})"
                _s(f"        {detail}")
    _s("")

    if wordless_drops:
        _s("--- WORDLESS FRAGMENT DROPS ---")
        _s(f"  {len(wordless_drops)} wordless keep fragment(s) removed at retake boundaries (VAD false-positives)")
        for d in wordless_drops:
            dur_ms = (d.end - d.start) * 1000
            _s(f"  {_ts(d.start)} → {_ts(d.end)}  ({dur_ms:.0f}ms)  {Path(d.source_clip).name}")
        _s("")

    _s("--- IMAGE OVERLAYS ---")
    if not config.images.enabled:
        _s("  (disabled)")
    elif image_cues is None:
        _s("  (not available — dry-run mode)")
    elif not image_cues:
        _s("  0 logos matched")
    else:
        _s(f"  {len(image_cues)} logo(s) detected")
        _s(f"  {'KEYWORD':<20}  {'OUTPUT TIME':<22}  FILE")
        _s(f"  {'─'*20}  {'─'*22}  {'─'*40}")
        for cue in image_cues:
            time_range = f"{_ts(cue.start)} → {_ts(cue.end)}"
            _s(f"  {cue.keyword:<20}  {time_range:<22}  {cue.image_path}")
    _s("")

    summary = edl_summary(edl)
    _s("--- EDL SUMMARY ---")
    _s(f"  Keep : {summary['total_keep_s']}s  ({summary['keep_segments']} segments)")
    cut_breakdown = "  ".join(
        f"{r}×{n}" for r, n in summary["reasons"].items() if n > 0
    )
    _s(f"  Cut  : {summary['total_cut_s']}s  — {cut_breakdown or 'none'}")
    _s("")

    _s("--- EDL ENTRIES ---")
    _s(f"  {'#':>4}  {'TIME RANGE':<22}  {'CLIP':<22}  {'KEEP':<5}  {'DUR':>7}  REASON")
    _s(f"  {'─'*4}  {'─'*22}  {'─'*22}  {'─'*5}  {'─'*7}  {'─'*10}")
    for i, entry in enumerate(edl):
        keep_str = "KEEP " if entry.keep else "CUT  "
        dur = entry.end - entry.start
        clip_name = Path(entry.source_clip).name
        _s(
            f"  {i:>4}  {_ts(entry.start):>9}→{_ts(entry.end):<11}  {clip_name:<22}"
            f"  {keep_str}  {dur:>6.3f}s  {entry.reason}"
        )

    Path(f"{base_path}.debug.6.summary.txt").write_text("\n".join(s) + "\n")

    # -------------------------------------------------------------------------
    # raw — raw Whisper output before alignment
    # -------------------------------------------------------------------------
    r: list[str] = [header]
    _r = r.append

    _r("--- RAW WHISPER OUTPUT ---")
    _r(f"  ({len(raw_words)} words total)")
    for w in raw_words:
        _r(f"  {_ts(w.start):>9} → {_ts(w.end):<9}  {w.word!r:<30}  conf={w.confidence:.2f}"
           f"  clip={Path(w.clip_path).name}")

    Path(f"{base_path}.debug.1.raw.txt").write_text("\n".join(r) + "\n")

    # -------------------------------------------------------------------------
    # sentences — raw Whisper words grouped by is_sentence_boundary, so the
    #             sentence split that drives captions/cuts can be eyeballed
    #             before any retranscription touches the words.
    # -------------------------------------------------------------------------
    from .transcriber import is_sentence_boundary

    pause_s = config.cuts.sentence_pause_s
    sb: list[str] = [header]
    _sb = sb.append
    _sb("--- SENTENCE BOUNDARIES (raw Whisper output grouped by is_sentence_boundary) ---")
    _sb(f"  Rule: ends with . ! ?   OR   capitalised next word after >= {pause_s:.2f}s pause"
        f"  (cuts.sentence_pause_s={pause_s})")
    n_sentences = 0
    for clip_path in clip_paths:
        clip_words = sorted(
            [w for w in raw_words if w.clip_path == str(clip_path)],
            key=lambda w: w.start,
        )
        sentences = _group_sentences(clip_words, is_sentence_boundary, pause_s)
        n_sentences += len(sentences)
        _sb(f"\n  Clip: {Path(clip_path).name}  ({len(clip_words)} words → {len(sentences)} sentences)")
        _sb(f"  {'#':>4}  {'TIME RANGE':<22}  {'WORDS':>5}  {'VIA':<11}  TEXT")
        _sb(f"  {'─'*4}  {'─'*22}  {'─'*5}  {'─'*11}  {'─'*50}")
        for i, (group, via) in enumerate(sentences, 1):
            time_range = f"{_ts(group[0].start)} → {_ts(group[-1].end)}"
            text = " ".join(w.word for w in group)
            _sb(f"  {i:>4}  {time_range:<22}  {len(group):>5}  {via:<11}  {text}")
    _sb(f"\n  ({n_sentences} sentences total)")

    Path(f"{base_path}.debug.1b.sentences.txt").write_text("\n".join(sb) + "\n")

    # -------------------------------------------------------------------------
    # post-align — after WhisperX alignment, before retranscription
    # -------------------------------------------------------------------------
    if post_align_words is not None:
        pa: list[str] = [header]
        _pa = pa.append
        _pa("--- POST-ALIGN OUTPUT (after WhisperX alignment, before VAD filter) ---")
        _pa(f"  ({len(post_align_words)} words)")

        if align_segments:
            _pa("")
            _pa(f"  WHISPERX SEGMENTS ({len(align_segments)} fed to wav2vec2):")
            _pa(f"  {'#':>4}  {'TIME RANGE':<22}  {'WORDS':>5}  TEXT")
            _pa(f"  {'─'*4}  {'─'*22}  {'─'*5}  {'─'*50}")
            for i, seg in enumerate(align_segments, 1):
                word_count = len(seg["text"].split())
                time_range = f"{_ts(seg['start'])} → {_ts(seg['end'])}"
                _pa(f"  {i:>4}  {time_range:<22}  {word_count:>5}  {seg['text']}")

        _pa("")
        _pa(f"  ALIGNED WORDS:")
        for w in post_align_words:
            _pa(f"  {_ts(w.start):>9} → {_ts(w.end):<9}  {w.word!r:<30}  conf={w.confidence:.2f}"
                f"  clip={Path(w.clip_path).name}")
        Path(f"{base_path}.debug.3.post-align.txt").write_text("\n".join(pa) + "\n")

    # -------------------------------------------------------------------------
    # post-retrans — after retranscription, before VAD filter
    # -------------------------------------------------------------------------
    if post_retrans_words is not None:
        pr: list[str] = [header]
        _pr = pr.append
        _pr("--- POST-RETRANS OUTPUT (after retranscription, before alignment) ---")
        _pr(f"  ({len(post_retrans_words)} words)")
        hard_capped_entries = [e for e in (retrans_log or []) if e.get("hard_capped")]
        if hard_capped_entries:
            _pr(f"")
            _pr(f"  ⚠ WARNING — {len(hard_capped_entries)} retranscription window(s) hit the 20s hard cap.")
            _pr(f"  The enclosing sentence exceeded 20s so the window was truncated mid-sentence.")
            _pr(f"  Consider reviewing the audio around these timestamps for unusually long sentences:")
            for e in hard_capped_entries:
                _pr(f"    [{_ts(e['win_start'])} → {_ts(e['win_end'])}]  trigger={e['label']}"
                    f"  (trigger was [{_ts(e.get('pre_exp_start', e['win_start']))} → {_ts(e.get('pre_exp_end', e['win_end']))}])")
            _pr(f"")
        for w in post_retrans_words:
            _pr(f"  {_ts(w.start):>9} → {_ts(w.end):<9}  {w.word!r:<30}  conf={w.confidence:.2f}"
                f"  clip={Path(w.clip_path).name}")
        Path(f"{base_path}.debug.2.post-retrans.txt").write_text("\n".join(pr) + "\n")

    # -------------------------------------------------------------------------
    # post-vad — after retranscription + alignment + VAD filter (final word list)
    # -------------------------------------------------------------------------
    a: list[str] = [header]
    _a = a.append

    total_dropped = sum(i["hallucinations_dropped"] for i in clip_info)
    _a("--- ALIGNED OUTPUT (after VAD hallucination filter — final word list) ---")
    _a(f"  ({len(aligned_words)} words kept, {total_dropped} dropped as hallucinations)")
    for w in aligned_words:
        keep_flag = "  [OUTTAKE]" if not w.keep else ""
        _a(f"  {_ts(w.start):>9} → {_ts(w.end):<9}  {w.word!r:<30}  conf={w.confidence:.2f}{keep_flag}")

    Path(f"{base_path}.debug.4.post-vad.txt").write_text("\n".join(a) + "\n")

    # -------------------------------------------------------------------------
    # timeline — words and gaps interleaved with cut reasoning
    # -------------------------------------------------------------------------
    t: list[str] = [header]
    _t = t.append

    _t("--- TIMELINE: WORDS + GAPS (source clip time) ---")

    edl_cut_boundaries: set[float] = set()
    for entry in edl:
        if not entry.keep:
            edl_cut_boundaries.add(round(entry.start, 3))

    for clip_path in clip_paths:
        clip_words = sorted(
            [w for w in aligned_words if w.clip_path == str(clip_path)],
            key=lambda w: w.start,
        )
        clip_gaps = gaps_by_clip.get(str(clip_path), [])
        gap_map = {(round(g.start, 4), round(g.end, 4)): g for g in clip_gaps}

        _t(f"\n  Clip: {Path(clip_path).name}  ({len(clip_words)} words, {len(clip_gaps)} gaps)")
        _t(f"  {'TIME RANGE':<22}  {'TYPE':<10}  {'CONTENT':<38}  DECISION")
        _t(f"  {'─'*22}  {'─'*10}  {'─'*38}  {'─'*30}")

        for i, w in enumerate(clip_words):
            keep_str = "KEEP" if w.keep else "CUT "
            dur_ms = (w.end - w.start) * 1000
            content = f"{w.word!r:<28}  conf={w.confidence:.2f}  {dur_ms:.0f}ms"
            short_note = ""
            if w.keep and dur_ms < 50 and i + 1 < len(clip_words):
                nxt_w = clip_words[i + 1]
                chk_gap = gap_map.get((round(w.end, 4), round(nxt_w.start, 4)))
                if chk_gap and chk_gap.cut:
                    short_note = f"  [!SHORT {dur_ms:.0f}ms]"
            _t(f"  {_ts(w.start):>9}→{_ts(w.end):<11}  {'WORD':<10}  {content:<38}  {keep_str}{short_note}")

            if i < len(clip_words) - 1:
                nxt = clip_words[i + 1]
                gap = gap_map.get((round(w.end, 4), round(nxt.start, 4)))
                if gap:
                    eff_note = (
                        f"  eff={_ts(gap.effective_start)}"
                        if abs(gap.effective_start - gap.start) > 0.005
                        else ""
                    )
                    g_content = f"{gap.gap_type.upper()}: {gap.duration_ms:.0f}ms{eff_note}"
                    if gap.cut:
                        # EDL uses gap.start (raw word end) as cut boundary, not
                        # effective_start — must compare the same value or a
                        # sub-ms offset between the two silently hides real cuts.
                        cut_key = round(gap.start, 3)
                        if cut_key not in edl_cut_boundaries:
                            decision = "KEEP [mid_sentence_floor]"
                        else:
                            decision = "CUT "
                    else:
                        decision = f"KEEP [{gap.skip_reason}]" if gap.skip_reason else "KEEP"
                    _t(f"  {_ts(gap.effective_start):>9}→{_ts(gap.end):<11}  {gap.gap_type.upper():<10}  {g_content:<38}  {decision}")
                elif nxt.start - w.end > 0.010:
                    dur_ms = (nxt.start - w.end) * 1000
                    _t(f"  {_ts(w.end):>9}→{_ts(nxt.start):<11}  {'(no gap)':<10}  {dur_ms:.0f}ms (below threshold)")

    Path(f"{base_path}.debug.5.timeline.txt").write_text("\n".join(t) + "\n")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _group_sentences(words, boundary_fn, pause_s):
    """Group consecutive words into sentences using boundary_fn.

    Returns a list of (words, via) where via labels the signal that closed the
    sentence: 'punct' (terminal . ! ?), 'caps+pause', or 'eos' (clip end).
    """
    if not words:
        return []
    groups: list[tuple[list, str]] = []
    current = [words[0]]
    for prev, w in zip(words, words[1:]):
        gap = w.start - prev.end
        if boundary_fn(prev.word, w.word, gap, pause_s):
            via = "punct" if boundary_fn(prev.word, None, 0, pause_s) else "caps+pause"
            groups.append((current, via))
            current = [w]
        else:
            current.append(w)
    groups.append((current, "eos"))
    return groups


def _ts(t: float) -> str:
    """Format seconds as M:SS.mmm or SS.mmms."""
    if t >= 60:
        m = int(t // 60)
        s = t % 60
        return f"{m}:{s:06.3f}"
    return f"{t:.3f}s"
