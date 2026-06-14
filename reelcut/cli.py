"""CLI — typer commands: transcribe (phase 1), render (phase 2), run (end-to-end)."""
from __future__ import annotations

# Fix: PyTorch OpenMP deadlock (issue #17199) — must be set before any torch/ctranslate2 import
import multiprocessing
import os
import sys

if sys.platform == "darwin":
    try:
        multiprocessing.set_start_method("spawn")
    except RuntimeError:
        pass
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")

import tempfile
import time
import traceback
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    name="reelcut",
    help="AI-powered CLI video editor for Instagram Reels.",
    no_args_is_help=True,
)
console = Console()
err_console = Console(stderr=True)


# ---------------------------------------------------------------------------
# reelcut transcribe  (Phase 1)
# ---------------------------------------------------------------------------

@app.command()
def transcribe(
    config_path: str = typer.Argument("config.yaml", help="Path to config.yaml"),
    slug: str | None = typer.Option(None, "--slug", help="Video slug (overrides script-derived slug)."),
    footage: str | None = typer.Option(None, "--footage", help="Path to footage file or folder."),
    clips_folder: str | None = typer.Option(None, "--clips-folder", help="Folder of ordered clips to stitch into one captions doc."),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Phase 1: transcribe footage → .captions.json files ready for LLM editing."""
    from .config import load_config
    try:
        cfg = load_config(config_path)
    except (FileNotFoundError, ValueError) as exc:
        err_console.print(f"[red]Config error:[/red] {exc}")
        raise typer.Exit(1)

    if not footage and not clips_folder:
        err_console.print("[red]Error:[/red] no footage specified — pass --footage <path> or --clips-folder <folder>")
        raise typer.Exit(1)

    slug = _resolve_slug(cfg, slug)
    output_dir = _assets_or_ts_dir(cfg, slug)

    if clips_folder:
        # Multi-clip mode: all clips → one captions doc
        clips = _collect_clips(clips_folder)
        stem = slug or Path(clips[0]).stem
        captions_path = output_dir / f"{stem}.captions.json"
        console.rule(f"[bold]Multi-clip → {captions_path.name}[/bold]")
        doc = _phase1(cfg, clips, output_dir, verbose)
        from .captions_doc import save_captions_doc
        save_captions_doc(doc, captions_path)
        console.print(f"[green]Captions doc →[/green] {captions_path}")
    else:
        input_folder = Path(footage)
        if input_folder.is_dir():
            # Folder mode: each video file → one captions doc
            videos = _list_videos(input_folder)
            if not videos:
                console.print(f"[yellow]No video files found in {input_folder}[/yellow]")
                raise typer.Exit(0)
            console.print(f"[bold]{len(videos)} video(s) to transcribe[/bold]\n")
            for i, video in enumerate(videos, 1):
                console.rule(f"[bold]{i}/{len(videos)}[/bold] {video.name}")
                captions_path = output_dir / f"{video.stem}.captions.json"
                try:
                    doc = _phase1(cfg, [str(video)], output_dir, verbose)
                    from .captions_doc import save_captions_doc
                    save_captions_doc(doc, captions_path)
                    console.print(f"[green]Captions doc →[/green] {captions_path}")
                except Exception as exc:
                    err_console.print(f"[red]Failed:[/red] {video.name} — {exc}")
                    if verbose:
                        err_console.print(traceback.format_exc())
        else:
            # Single video
            clips = [str(input_folder)]
            stem = slug or input_folder.stem
            captions_path = output_dir / f"{stem}.captions.json"
            doc = _phase1(cfg, clips, output_dir, verbose)
            from .captions_doc import save_captions_doc
            save_captions_doc(doc, captions_path)
            console.print(f"[green]Captions doc →[/green] {captions_path}")

    console.print(
        "\n[bold]Next:[/bold] edit the .captions.json (fix captions, add images entries), "
        "then run [cyan]reelcut render config.yaml <captions.json>[/cyan]"
    )


# ---------------------------------------------------------------------------
# reelcut render  (Phase 2)
# ---------------------------------------------------------------------------

@app.command()
def render(
    config_path: str = typer.Argument("config.yaml", help="Path to config.yaml"),
    captions_path: str = typer.Argument(..., help="Path to .captions.json from transcribe step"),
    slug: str | None = typer.Option(None, "--slug", help="Video slug (overrides script-derived slug)."),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Phase 2: render final video from a (possibly LLM-edited) .captions.json."""
    from .captions_doc import load_captions_doc
    from .config import load_config
    try:
        cfg = load_config(config_path)
    except (FileNotFoundError, ValueError) as exc:
        err_console.print(f"[red]Config error:[/red] {exc}")
        raise typer.Exit(1)

    cap_path = Path(captions_path)
    if not cap_path.exists():
        err_console.print(f"[red]Error:[/red] captions file not found: {cap_path}")
        raise typer.Exit(1)

    doc = load_captions_doc(cap_path)
    slug = _resolve_slug(cfg, slug) or cap_path.parent.name
    out_dir = Path(cfg.output.location)
    out_dir.mkdir(parents=True, exist_ok=True)
    output_path = out_dir / f"{slug}.mp4"

    console.rule(f"[bold]Rendering → {output_path}[/bold]")
    _phase2(cfg, doc, output_path, verbose)


# ---------------------------------------------------------------------------
# reelcut run  (end-to-end convenience)
# ---------------------------------------------------------------------------

@app.command()
def run(
    config_path: str = typer.Argument("config.yaml", help="Path to config.yaml"),
    footage: str = typer.Option(..., "--footage", help="Path to folder of footage files."),
    slug: str | None = typer.Option(None, "--slug", help="Video slug (overrides script-derived slug)."),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Run phase 1 only (no render)."),
) -> None:
    """End-to-end: transcribe + render without LLM editing step. Moves footage to done/."""
    from .captions_doc import save_captions_doc
    from .config import load_config
    try:
        cfg = load_config(config_path)
    except (FileNotFoundError, ValueError) as exc:
        err_console.print(f"[red]Config error:[/red] {exc}")
        raise typer.Exit(1)

    input_folder = Path(footage)
    if not input_folder.is_dir():
        err_console.print(f"[red]Error:[/red] --footage must be a folder: {input_folder}")
        raise typer.Exit(1)

    videos = _list_videos(input_folder)
    if not videos:
        console.print(f"[yellow]No video files found in {input_folder}[/yellow]")
        raise typer.Exit(0)

    done_dir = Path("done")
    done_dir.mkdir(exist_ok=True)

    slug = _resolve_slug(cfg, slug)
    assets_dir = _assets_or_ts_dir(cfg, slug)
    vid_out_dir = Path(cfg.output.location)
    vid_out_dir.mkdir(parents=True, exist_ok=True)

    console.print(f"[bold]{len(videos)} video(s) to process[/bold]\n")

    all_warnings: list[str] = []
    for i, video in enumerate(videos, 1):
        console.rule(f"[bold]{i}/{len(videos)}[/bold] {video.name}")
        stem = slug or video.stem
        out_path = vid_out_dir / f"{stem}.mp4"
        cap_path = assets_dir / f"{stem}.captions.json"

        try:
            doc = _phase1(cfg, [str(video)], assets_dir, verbose)
            save_captions_doc(doc, cap_path)

            if dry_run:
                console.print(f"[yellow]--dry-run:[/yellow] skipping render. Captions → {cap_path}")
                continue

            warnings = _phase2(cfg, doc, out_path, verbose)
            all_warnings.extend(warnings)
        except Exception as exc:
            err_console.print(f"[red]Failed:[/red] {video.name} — {exc}")
            if verbose:
                err_console.print(traceback.format_exc())
            continue

        dest = done_dir / video.name
        if dest.exists():
            dest = done_dir / f"{video.stem}_{int(dest.stat().st_mtime)}{video.suffix}"
        video.rename(dest)
        console.print(f"[cyan]Moved {video.name} → done/{dest.name}[/cyan]\n")

    _exit_with_warnings(all_warnings)


# ---------------------------------------------------------------------------
# reelcut preview-edl
# ---------------------------------------------------------------------------

@app.command(name="preview-edl")
def preview_edl(
    captions_path: str = typer.Argument(..., help="Path to .captions.json file."),
) -> None:
    """Print a summary of the EDL embedded in a .captions.json file."""
    from .captions_doc import load_captions_doc

    path = Path(captions_path)
    if not path.exists():
        err_console.print(f"[red]Error:[/red] file not found: {path}")
        raise typer.Exit(1)

    doc = load_captions_doc(path)

    keep_entries = [e for e in doc.edl if e.keep]
    cut_entries = [e for e in doc.edl if not e.keep]
    total_keep_s = round(sum(e.end - e.start for e in keep_entries), 2)
    total_cut_s = round(sum(e.end - e.start for e in cut_entries), 2)

    console.print(f"\n[bold]Captions doc:[/bold] {captions_path}")
    console.print(f"  Words         : {len(doc.words)}")
    console.print(f"  Keep segments : {len(keep_entries)}")
    console.print(f"  Cut segments  : {len(cut_entries)}")
    console.print(f"  Keep duration : [green]{total_keep_s}s[/green]")
    console.print(f"  Cut duration  : [red]{total_cut_s}s[/red]")
    console.print(f"  Images        : {len(doc.images)}")

    table = Table("#", "Clip", "Start", "End", "Duration", "Keep", "Reason")
    for i, entry in enumerate(doc.edl):
        keep_str = "[green]KEEP[/green]" if entry.keep else "[red]CUT[/red]"
        dur = round(entry.end - entry.start, 3)
        table.add_row(
            str(i),
            Path(entry.source_clip).name,
            f"{entry.start:.3f}s",
            f"{entry.end:.3f}s",
            f"{dur}s",
            keep_str,
            entry.reason,
        )
    console.print(table)


# ---------------------------------------------------------------------------
# reelcut timeline
# ---------------------------------------------------------------------------

@app.command()
def timeline(
    captions_path: str = typer.Argument(..., help="Path to .captions.json file"),
) -> None:
    """Print output-timeline word positions remapped from the current EDL."""
    from .captions_doc import load_captions_doc
    from .edl import EDLEntry
    from .transcriber import WordTimestamp

    path = Path(captions_path)
    if not path.exists():
        err_console.print(f"[red]Error:[/red] file not found: {path}")
        raise typer.Exit(1)

    doc = load_captions_doc(path)

    edl = [
        EDLEntry(start=e.start, end=e.end, keep=e.keep, source_clip=e.source_clip, reason=e.reason)
        for e in doc.edl
    ]
    source_words = [
        WordTimestamp(word=w.word, start=w.start, end=w.end, confidence=1.0, clip_path=w.source_clip)
        for w in doc.words
    ]
    output_words = _remap_kept_words(source_words, edl)

    total = output_words[-1].end if output_words else 0.0
    console.print(f"\n[bold]Output timeline[/bold] — {len(output_words)} words, {total:.2f}s total\n")
    for w in output_words:
        console.print(f"  {w.start:>8.3f}s → {w.end:<8.3f}s  {w.word}")


# ---------------------------------------------------------------------------
# Phase 1 — transcription core
# ---------------------------------------------------------------------------

def _phase1(cfg, clips: list[str], output_dir: Path, verbose: bool):
    """Transcribe clips, build EDL, return CaptionsDoc. No rendering."""
    from .audio import extract_audio, normalize_audio
    from .captions_doc import CaptionWord, CaptionsDoc, EdlEntry
    from .edl import generate_scriptless_edl, edl_summary
    from .gap_detector import detect_gaps
    from .transcriber import transcribe as do_transcribe, align, filter_words_by_vad, filter_silent_words, WordTimestamp

    # Build a video-specific initial_prompt by appending the slug (converted to
    # natural text) to the base prompt from config. This biases Whisper toward
    # proper nouns and technical terms in the video title — e.g. "claude" over
    # "cloud", "caching" spelled correctly, etc. — without losing the general
    # vocabulary hint set in config.yaml.
    slug_text = " ".join(
        w.capitalize()
        for w in output_dir.name.replace("-", " ").replace("_", " ").split()
    )
    base_prompt = cfg.whisper.initial_prompt or ""
    combined_prompt = f"{base_prompt}, {slug_text}" if base_prompt else slug_text
    whisper_cfg = cfg.whisper.model_copy(update={"initial_prompt": combined_prompt})
    console.print(f"  Whisper prompt: {combined_prompt!r}")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        all_words: list = []
        all_raw_words: list = []
        all_post_align_words: list = []
        all_post_retrans_words: list = []
        all_align_segments: list[dict] = []
        clip_info: list[dict] = []
        retrans_log: list[dict] = []

        for clip_path in clips:
            wav = tmp / (Path(clip_path).stem + ".wav")

            console.print(f"[bold]Step 1[/bold] Extracting audio: {Path(clip_path).name}…")
            t = time.perf_counter()
            extract_audio(clip_path, wav)
            normalize_audio(wav)
            _tlog(time.perf_counter() - t, "done")

            console.print(f"[bold]Step 2[/bold] Transcribing {Path(clip_path).name}…")
            t = time.perf_counter()
            words = do_transcribe(wav, whisper_cfg)
            _tlog(time.perf_counter() - t, f"{len(words)} words")

            for w in words:
                w.clip_path = str(clip_path)
            all_raw_words.extend(words)

            console.print(f"[bold]Step 3[/bold] Retranscribing suspicious regions in {Path(clip_path).name}…")
            t = time.perf_counter()
            from .transcriber import retranscribe_suspicious_regions
            clips_dir = output_dir / "retranscribe-clips"
            words, n_retrans, clip_retrans_log = retranscribe_suspicious_regions(
                words, wav, whisper_cfg,
                conf_threshold=cfg.cuts.min_retrans_word_confidence,
                rescue_floor=cfg.cuts.retrans_rescue_floor,
                clips_dir=clips_dir,
                silence_threshold_db=cfg.cuts.silence_threshold_db,
                min_silence_ms=cfg.cuts.min_silence_ms,
                failure_tolerance_ratio=cfg.cuts.failure_tolerance_ratio,
            )
            retrans_log.extend(clip_retrans_log)
            if n_retrans:
                words.sort(key=lambda w: w.start)
                console.print(f"  Retranscribed {n_retrans} suspicious window(s)")
                _warn_wide_words(words, console, cfg.whisper.wide_word_threshold_s)
            all_post_retrans_words.extend([
                w.__class__(word=w.word, start=w.start, end=w.end,
                             confidence=w.confidence, clip_path=str(clip_path))
                for w in words
            ])

            console.print(f"[bold]Step 4[/bold] Aligning timestamps for {Path(clip_path).name}…")
            words, align_method, clip_align_segments = align(words, wav, whisper_cfg)
            all_align_segments.extend(clip_align_segments)
            align_ok = "Whisper timestamps" not in align_method
            align_color = "green" if align_ok else "yellow"
            console.print(f"  Alignment: [{align_color}]{align_method}[/{align_color}]")
            words.sort(key=lambda w: w.start)
            _warn_wide_words(words, console, cfg.whisper.wide_word_threshold_s)
            all_post_align_words.extend([
                w.__class__(word=w.word, start=w.start, end=w.end,
                             confidence=w.confidence, clip_path=str(clip_path))
                for w in words
            ])

            before = len(words)
            try:
                words = filter_words_by_vad(words, wav, threshold=cfg.cuts.vad_threshold)
                vad_method = "Silero VAD (ONNX)"
                vad_color = "green"
            except Exception as exc:
                console.print(f"  [yellow]VAD filter failed ({exc}) — falling back to energy filter[/yellow]")
                words = filter_silent_words(words, wav, cfg.cuts.silence_threshold_db, cfg.cuts.failure_tolerance_ratio)
                vad_method = "energy filter (fallback)"
                vad_color = "yellow"
            dropped = before - len(words)
            drop_note = f", [red]{dropped} hallucinated words dropped[/red]" if dropped else ", no hallucinations detected"
            console.print(f"  Hallucination filter: [{vad_color}]{vad_method}[/{vad_color}]{drop_note}")
            _tlog(time.perf_counter() - t, f"{len(words)} words")

            for w in words:
                w.clip_path = str(clip_path)
            all_words.extend(words)
            clip_info.append({
                "clip": str(clip_path),
                "align_method": align_method,
                "vad_method": vad_method,
                "hallucinations_dropped": dropped,
            })

        # Retake detection
        retake_ranges: dict[str, list[tuple[float, float]]] = {}
        retake_candidates: dict[str, list] = {}
        if cfg.cuts.repetition_detection:
            from .retake_detector import detect_retakes
            console.print("[bold]Step 4b[/bold] Detecting duplicate takes…")
            t = time.perf_counter()
            for clip_path in clips:
                clip_words = [w for w in all_words if w.clip_path == str(clip_path)]
                ranges, candidates = detect_retakes(
                    clip_words,
                    cfg.cuts.min_retake_words,
                    cfg.cuts.max_retake_gap_s,
                    cfg.cuts.min_match_ratio,
                    cfg.cuts.max_retake_bridge_s,
                )
                if ranges:
                    retake_ranges[str(clip_path)] = ranges
                if candidates:
                    retake_candidates[str(clip_path)] = candidates
            total_retakes = sum(len(v) for v in retake_ranges.values())
            if total_retakes:
                total_s = sum(e - s for v in retake_ranges.values() for s, e in v)
                console.print(f"  {total_retakes} retake region(s) detected ({total_s:.1f}s to cut)")
            else:
                console.print("  No duplicate takes found")
            _tlog(time.perf_counter() - t)

        # Gap detection
        console.print("[bold]Step 5[/bold] Detecting silences, breaths, and gaps…")
        t = time.perf_counter()
        gaps = []
        gaps_by_clip: dict[str, list] = {}
        for clip_path in clips:
            wav = tmp / (Path(clip_path).stem + ".wav")
            clip_words = [w for w in all_words if w.clip_path == str(clip_path)]
            clip_gaps = detect_gaps(clip_words, wav, cfg.cuts)
            gaps_by_clip[str(clip_path)] = clip_gaps
            gaps.extend(clip_gaps)
        n_cut_total = sum(1 for g in gaps if g.cut)
        _tlog(time.perf_counter() - t, f"{n_cut_total}/{len(gaps)} gaps cut")

        # EDL generation
        console.print("[bold]Step 6[/bold] Building EDL…")
        t = time.perf_counter()
        warnings: list[str] = []
        edl = generate_scriptless_edl(all_words, gaps, min_keep_ms=cfg.cuts.min_keep_ms, speech_pad_ms=cfg.cuts.speech_pad_ms, mid_sentence_cut_floor_ms=cfg.cuts.mid_sentence_cut_floor_ms)

        wordless_drops: list = []
        if retake_ranges:
            from .edl import apply_retake_cuts
            edl, wordless_drops = apply_retake_cuts(edl, retake_ranges, all_words)

        summary = edl_summary(edl)
        console.print(
            f"({time.perf_counter() - t:.1f}s) "
            f"[green]keep {summary['total_keep_s']}s[/green] / "
            f"[red]cut {summary['total_cut_s']}s[/red]"
        )

        if summary["total_keep_s"] > cfg.output.max_duration_s:
            warnings.append(
                f"Output duration {summary['total_keep_s']}s exceeds max_duration_s={cfg.output.max_duration_s}s"
            )

        # Remap words to output timeline
        caption_words = _remap_kept_words(all_words, edl)

        if warnings:
            for w in warnings:
                console.print(f"  [yellow]Warning:[/yellow] {w}")

        # Debug report
        from .debug_report import write_debug_report
        debug_base = output_dir / Path(clips[0]).stem
        write_debug_report(
            debug_base,
            clip_paths=clips,
            config=cfg,
            raw_words=all_raw_words,
            post_align_words=all_post_align_words,
            align_segments=all_align_segments,
            post_retrans_words=all_post_retrans_words,
            aligned_words=all_words,
            gaps_by_clip=gaps_by_clip,
            edl=edl,
            caption_words=caption_words,
            clip_info=clip_info,
            retrans_log=retrans_log,
            retake_ranges=retake_ranges,
            retake_candidates=retake_candidates,
            wordless_drops=wordless_drops,
            image_cues=None,
        )
        console.print(f"[green]Debug report  →[/green] {debug_base}.debug.{{1.raw,2.post-retrans,3.post-align,4.post-vad,5.timeline,6.summary}}.txt")

        # Build captions doc
        doc_edl = [
            EdlEntry(
                source_clip=e.source_clip,
                start=round(e.start, 4),
                end=round(e.end, 4),
                keep=e.keep,
                reason=e.reason,
            )
            for e in edl
        ]
        doc_words = [
            CaptionWord(word=w.word, start=w.start, end=w.end, source_clip=w.clip_path)
            for w in all_words
            if w.keep
        ]
        return CaptionsDoc(
            source_clips=clips,
            edl=doc_edl,
            words=doc_words,
            images=[],
        )


# ---------------------------------------------------------------------------
# Phase 2 — render core
# ---------------------------------------------------------------------------

def _phase2(cfg, doc, output_path: Path, verbose: bool) -> list[str]:
    """Render final video from a CaptionsDoc. Returns warnings."""
    from .caption import render_caption_frames
    from .captions_doc import ImageSpec
    from .edl import EDLEntry
    from .image_finder import ImageCue, detect_image_cues
    from .renderer import render as do_render
    from .transcriber import WordTimestamp

    warnings: list[str] = []
    output_dir = output_path.parent

    # Convert EdlEntry (captions_doc) → EDLEntry (edl module) for renderer
    edl = [
        EDLEntry(
            start=e.start,
            end=e.end,
            keep=e.keep,
            source_clip=e.source_clip,
            reason=e.reason,
        )
        for e in doc.edl
    ]

    # Remap source-clip-time words to output-timeline using current EDL
    source_words = [
        WordTimestamp(word=w.word, start=w.start, end=w.end, confidence=1.0, clip_path=w.source_clip)
        for w in doc.words
    ]
    caption_words = _remap_kept_words(source_words, edl)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        # Caption frames
        caption_frames = []
        if cfg.captions.enabled and cfg.captions.style != "none":
            console.print("[bold]Step 6a/6[/bold] Rendering caption frames…")
            t = time.perf_counter()
            cap_dir = tmp / "captions"
            caption_frames = render_caption_frames(
                caption_words, cfg.captions, cap_dir,
                fps=cfg.output.fps,
                resolution=tuple(cfg.output.resolution),
            )
            _tlog(time.perf_counter() - t, f"{len(caption_frames)} frames")

        # Image cues: logos (auto-detected from words) + people/screenshots (from captions doc)
        all_image_cues: list[ImageCue] = []
        if cfg.images.enabled:
            logo_cues = detect_image_cues(caption_words, cfg.images)
            all_image_cues.extend(logo_cues)
            if logo_cues:
                console.print(f"  Logos detected: {[c.keyword for c in logo_cues]}")

            remap, clip_order = _build_edl_remap(edl)
            fallback_clip = clip_order[0] if clip_order else ""
            for spec in doc.images:
                clip = spec.source_clip or fallback_clip
                remapped_start = remap(clip, spec.start)
                remapped_end = remap(clip, spec.end)
                remapped_spec = type(spec)(
                    type=spec.type,
                    start=remapped_start,
                    end=remapped_end,
                    source_clip=clip,
                    name=spec.name,
                    path=spec.path,
                )
                cue = _resolve_image_spec(remapped_spec, cfg.images.display_duration_s)
                if cue:
                    all_image_cues.append(cue)

        if cfg.images.enabled and all_image_cues:
            console.print(f"[bold]Step 6b/6[/bold] Rendering image overlays ({len(all_image_cues)} total)…")
            t = time.perf_counter()
            from .image_overlay import render_image_frames, merge_with_caption_frames
            img_dir = tmp / "image_frames"
            image_frames = render_image_frames(
                all_image_cues, cfg.images, img_dir,
                fps=cfg.output.fps,
                resolution=tuple(cfg.output.resolution),
            )
            caption_frames = merge_with_caption_frames(
                caption_frames, image_frames, tuple(cfg.output.resolution),
            )
            _tlog(time.perf_counter() - t)

        # Final render
        from .renderer import _USE_VIDEOTOOLBOX
        encoder = "h264_videotoolbox (hardware)" if _USE_VIDEOTOOLBOX else "libx264 (software)"
        console.print(f"[bold]Step 6c/6[/bold] Rendering final video… encoder: [cyan]{encoder}[/cyan]")
        t = time.perf_counter()
        out = do_render(edl, caption_frames, cfg, output_path)
        console.print(f"\n[green bold]Done![/green bold] → {out}  ({time.perf_counter() - t:.1f}s)")

    return warnings


def _resolve_image_spec(spec, display_duration_s: float):
    """Resolve an ImageSpec from the captions doc to an ImageCue."""
    from .image_finder import ImageCue

    if spec.type == "person":
        if not spec.name:
            return None
        from .entity_resolver import resolve_entity_image
        img = resolve_entity_image(spec.name, "person")
        if img is None:
            console.print(f"  [yellow]Could not resolve Wikipedia image for: {spec.name}[/yellow]")
            return None
        return ImageCue(
            keyword=spec.name,
            start=spec.start,
            end=spec.end,
            image_path=str(img),
            type="person",
        )

    elif spec.type == "screenshot":
        if not spec.path:
            return None
        p = Path(spec.path)
        if not p.exists():
            console.print(f"  [yellow]Screenshot not found: {spec.path}[/yellow]")
            return None
        return ImageCue(
            keyword=f"{p.parent.name}_{p.stem}",
            start=spec.start,
            end=spec.end,
            image_path=str(p),
            type="screenshot",
        )

    else:
        console.print(f"  [yellow]Unknown image type: {spec.type}[/yellow]")
        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_slug(cfg, slug_arg: str | None) -> str | None:
    if slug_arg:
        return slug_arg
    return None


def _assets_or_ts_dir(cfg, slug: str | None) -> Path:
    """Return assets/<slug>/ if slug is known, otherwise output/<timestamp>/."""
    if slug:
        d = Path(cfg.assets.location) / slug
    else:
        d = Path(cfg.output.location) / time.strftime("%Y-%m-%d_%H-%M-%S")
    d.mkdir(parents=True, exist_ok=True)
    return d


def _list_videos(folder: Path) -> list[Path]:
    video_exts = {".mp4", ".mov", ".mkv"}
    return sorted(
        [p for p in folder.iterdir() if p.suffix.lower() in video_exts],
        key=lambda p: p.stat().st_mtime,
    )


def _collect_clips(clips_folder: str) -> list[str]:
    folder = Path(clips_folder)
    clips = _list_videos(folder)
    if not clips:
        raise typer.BadParameter(f"No video files found in --clips-folder: {folder}")
    return [str(c) for c in clips]


def _build_edl_remap(edl: list):
    """Pre-compute EDL remap tables. Returns callable (source_clip, t) -> output_t."""
    clip_order: list[str] = []
    for entry in edl:
        if entry.source_clip not in clip_order:
            clip_order.append(entry.source_clip)

    keep_dur: dict[str, float] = {}
    first_keep_start: dict[str, float] = {}
    cut_intervals: dict[str, list[tuple[float, float]]] = {}

    for entry in edl:
        c = entry.source_clip
        if entry.keep:
            keep_dur[c] = keep_dur.get(c, 0.0) + (entry.end - entry.start)
            if c not in first_keep_start:
                first_keep_start[c] = entry.start
        else:
            cut_intervals.setdefault(c, []).append((entry.start, entry.end))

    clip_base: dict[str, float] = {}
    acc = 0.0
    for c in clip_order:
        clip_base[c] = acc
        acc += keep_dur.get(c, 0.0)

    def remap(source_clip: str, t: float) -> float:
        cuts = cut_intervals.get(source_clip, [])
        first_start = first_keep_start.get(source_clip, 0.0)
        cut_offset = sum(e - s for s, e in cuts if s >= first_start and e <= t)
        intra = t - first_start - cut_offset
        return round(max(0.0, clip_base.get(source_clip, 0.0) + intra), 4)

    return remap, clip_order


def _remap_kept_words(words: list, edl: list) -> list:
    """Remap kept WordTimestamp objects from source clip time to output video time."""
    from .transcriber import WordTimestamp

    remap, _ = _build_edl_remap(edl)
    remapped = []
    for w in words:
        if not w.keep:
            continue
        new_start = remap(w.clip_path, w.start)
        new_end = new_start + (w.end - w.start)
        remapped.append(WordTimestamp(
            word=w.word,
            start=round(max(0.0, new_start), 4),
            end=round(max(0.0, new_end), 4),
            confidence=w.confidence,
            clip_path=w.clip_path,
        ))

    return sorted(remapped, key=lambda w: w.start)


_WIDE_WORD_THRESHOLD_S = 1.5


def _warn_wide_words(words: list, console: Console, threshold_s: float = _WIDE_WORD_THRESHOLD_S) -> None:
    wide = [(w, w.end - w.start) for w in words if (w.end - w.start) >= threshold_s]
    if not wide:
        return
    console.print(f"  [yellow]⚠ {len(wide)} suspiciously wide word(s) — likely missed speech:[/yellow]")
    for w, span in wide:
        start_m, start_s = divmod(w.start, 60)
        end_m, end_s = divmod(w.end, 60)
        console.print(
            f"    [yellow]\"{w.word}\"[/yellow]  "
            f"{int(start_m)}:{start_s:05.2f} → {int(end_m)}:{end_s:05.2f}  "
            f"([yellow]{span:.1f}s[/yellow])"
        )


def _tlog(elapsed: float, label: str = "") -> None:
    msg = f"  → {label} ({elapsed:.1f}s)" if label else f"  → {elapsed:.1f}s"
    console.print(msg)


def _vlog(verbose: bool, msg: str) -> None:
    if verbose:
        console.print(f"[cyan]{msg}[/cyan]")


def _exit_with_warnings(warnings: list[str]) -> None:
    if warnings:
        err_console.print(f"\n[yellow]{len(warnings)} warning(s):[/yellow]")
        for w in warnings:
            err_console.print(f"  [yellow]·[/yellow] {w}")
        raise typer.Exit(2)
