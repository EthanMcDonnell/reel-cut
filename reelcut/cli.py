"""CLI — typer commands: init, run, transcribe, preview-edl."""
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
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")  # macOS: suppress duplicate OpenMP runtime error
os.environ.setdefault("OMP_NUM_THREADS", "1")          # prevent OMP fork-safety segfault (ctranslate2 + torch)

import json
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
# reelcut init
# ---------------------------------------------------------------------------

@app.command()
def init(
    output: str = typer.Option("config.yaml", "--output", "-o", help="Path for the generated config file."),
) -> None:
    """Generate a default config.yaml in the current directory."""
    from .config import generate_default_config

    try:
        path = generate_default_config(output)
        console.print(f"[green]Created[/green] {path}")
        console.print("Edit the [bold]input.footage[/bold] and [bold]input.script[/bold] fields, then run:")
        console.print(f"  reelcut run {path}")
    except FileExistsError as exc:
        err_console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# reelcut run
# ---------------------------------------------------------------------------

@app.command()
def run(
    config_path: str = typer.Argument("config.yaml", help="Path to config.yaml"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Generate EDL without rendering."),
) -> None:
    """Process all videos in input.footage folder, moving each to done/ when complete."""
    from .config import load_config
    try:
        cfg = load_config(config_path)
    except (FileNotFoundError, ValueError) as exc:
        err_console.print(f"[red]Config error:[/red] {exc}")
        raise typer.Exit(1)

    input_folder = Path(cfg.input.footage)
    if not input_folder.is_dir():
        err_console.print(f"[red]Error:[/red] input.footage must be a folder: {input_folder}")
        raise typer.Exit(1)

    if cfg.input.script is not None:
        script_path = Path(cfg.input.script)
        if not script_path.exists():
            err_console.print(f"[red]Error:[/red] script not found: {script_path}")
            raise typer.Exit(1)

    video_exts = {".mp4", ".mov", ".mkv"}
    videos = sorted(
        [p for p in input_folder.iterdir() if p.suffix.lower() in video_exts],
        key=lambda p: p.stat().st_mtime,
    )

    if not videos:
        console.print(f"[yellow]No video files found in {input_folder}[/yellow]")
        raise typer.Exit(0)

    done_dir = Path("done")
    done_dir.mkdir(exist_ok=True)

    output_dir = Path(cfg.output.location)
    output_dir.mkdir(parents=True, exist_ok=True)

    console.print(f"[bold]{len(videos)} video(s) to process[/bold]\n")

    all_warnings: list[str] = []
    for i, video in enumerate(videos, 1):
        console.rule(f"[bold]{i}/{len(videos)}[/bold] {video.name}")

        cfg.input.footage = str(video)
        out_path = output_dir / f"{video.stem}.mp4"

        try:
            warnings = _run_pipeline(cfg, out_path, verbose, dry_run)
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


def _run_pipeline(cfg, output_path: Path, verbose: bool, dry_run: bool) -> list[str]:
    """Run the full pipeline for a single configured footage file. Returns warnings."""
    from .audio import extract_audio, normalize_audio
    from .caption import render_caption_frames
    from .edl import generate_scriptless_edl, generate_edl, save_edl, edl_summary
    from .gap_detector import detect_gaps
    from .renderer import render as do_render
    from .transcriber import transcribe, align, filter_words_by_vad, filter_silent_words

    warnings: list[str] = []
    output_dir = output_path.parent
    use_script = cfg.input.script is not None

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        clips = _collect_clips(cfg)
        all_words = []

        for clip_path in clips:
            wav = tmp / (Path(clip_path).stem + ".wav")

            # --- Audio extraction ---
            console.print(f"[bold]Step 1[/bold] Extracting audio: {Path(clip_path).name}…")
            _vlog(verbose, f"  → {wav}")
            t = time.perf_counter()
            extract_audio(clip_path, wav)
            normalize_audio(wav)
            _tlog(time.perf_counter() - t, "done")

            # --- Transcription ---
            console.print(f"[bold]Step 2[/bold] Transcribing {Path(clip_path).name}…")
            t = time.perf_counter()
            words = transcribe(wav, cfg.whisper)
            _tlog(time.perf_counter() - t, f"{len(words)} words")
            _vlog(verbose, f"  {len(words)} words from faster-whisper")

            # --- Forced alignment ---
            console.print(f"[bold]Step 3[/bold] Aligning timestamps for {Path(clip_path).name}…")
            t = time.perf_counter()
            words, align_method = align(words, wav, cfg.whisper)
            align_ok = "Whisper timestamps" not in align_method
            align_color = "green" if align_ok else "yellow"
            console.print(f"  Alignment: [{align_color}]{align_method}[/{align_color}]")

            # --- VAD hallucination filter ---
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

        transcript_path = output_dir / f"{output_path.stem}.transcript.json"

        # --- Retake detection (scriptless only — script mode handles this via last-take-wins) ---
        retake_ranges: dict[str, list[tuple[float, float]]] = {}
        if not use_script and cfg.cuts.min_retake_words > 0:
            from .retake_detector import detect_retakes
            console.print("[bold]Step 3b[/bold] Detecting duplicate takes…")
            t = time.perf_counter()
            for clip_path in clips:
                clip_words = [w for w in all_words if w.clip_path == str(clip_path)]
                ranges = detect_retakes(clip_words, cfg.cuts.min_retake_words)
                if ranges:
                    retake_ranges[str(clip_path)] = ranges
                    _vlog(verbose, f"  {Path(clip_path).name}: {len(ranges)} retake region(s) found")
            total_retakes = sum(len(v) for v in retake_ranges.values())
            if total_retakes:
                total_s = sum(e - s for v in retake_ranges.values() for s, e in v)
                console.print(f"  {total_retakes} retake region(s) detected ({total_s:.1f}s to cut)")
            else:
                console.print("  No duplicate takes found")
            _tlog(time.perf_counter() - t)

        # --- Gap detection (always runs — primary cut driver) ---
        console.print("[bold]Step 4[/bold] Detecting silences, breaths, and gaps…")
        t = time.perf_counter()
        gaps = []
        for clip_path in clips:
            wav = tmp / (Path(clip_path).stem + ".wav")
            clip_words = [w for w in all_words if w.clip_path == str(clip_path)]
            clip_gaps = detect_gaps(clip_words, wav, cfg.cuts)
            gaps.extend(clip_gaps)
            n_cut = sum(1 for g in clip_gaps if g.cut)
            _vlog(verbose, f"  {Path(clip_path).name}: {n_cut}/{len(clip_gaps)} gaps will be cut")
        n_cut_total = sum(1 for g in gaps if g.cut)
        _tlog(time.perf_counter() - t, f"{n_cut_total}/{len(gaps)} gaps cut")

        # --- EDL generation ---
        console.print("[bold]Step 5[/bold] Building EDL…")
        t = time.perf_counter()
        if use_script:
            # Script mode: gap cuts + outtake removal
            from .script_aligner import align_to_script
            console.print("  Script provided — removing outtakes…")
            result = align_to_script(all_words, cfg.input.script)

            if result.missing_lines:
                msg = f"{len(result.missing_lines)} script word(s) have no matching footage: {result.missing_lines[:5]}"
                warnings.append(msg)
                console.print(f"  [yellow]Warning:[/yellow] {msg}")

            total_words = len(all_words)
            outtake_words = sum(len(o) for o in result.outtakes)
            if total_words > 0:
                outtake_pct = outtake_words / total_words * 100
                _vlog(verbose, f"  {len(result.segments)} segments, {outtake_pct:.0f}% outtakes")
                if outtake_pct > 30:
                    msg = (
                        f"{outtake_pct:.0f}% of transcript was not matched to the script "
                        "and will be cut. Check your script matches what you recorded."
                    )
                    warnings.append(msg)
                    console.print(f"  [yellow]Warning:[/yellow] {msg}")

            edl = generate_edl(result.segments, gaps, all_words, min_keep_ms=cfg.cuts.min_keep_ms)
        else:
            # Scriptless mode: gap cuts only, all speech kept
            console.print("  No script — keeping all speech, cutting silences/breaths…")
            edl = generate_scriptless_edl(all_words, gaps, min_keep_ms=cfg.cuts.min_keep_ms, speech_pad_ms=cfg.cuts.speech_pad_ms)

        # Apply retake cuts (works in both script and scriptless modes)
        if retake_ranges:
            from .edl import apply_retake_cuts
            edl = apply_retake_cuts(edl, retake_ranges, all_words)

        # Transcript artifact — written after EDL so keep=True/False reflects final decisions
        transcript_data = [
            {
                "word": w.word,
                "start": round(w.start, 3),
                "end": round(w.end, 3),
                "confidence": round(w.confidence, 3),
                "clip": Path(w.clip_path).name,
                "keep": w.keep,
            }
            for w in all_words
        ]
        transcript_path.write_text(json.dumps(transcript_data, indent=2))
        console.print(f"  Transcript → {transcript_path}  ({len(all_words)} words, {sum(1 for w in all_words if w.keep)} kept)")

        edl_path = output_dir / f"{output_path.stem}.edl.json"
        save_edl(edl, edl_path)
        summary = edl_summary(edl)
        console.print(
            f"({time.perf_counter() - t:.1f}s) "
            f"[green]keep {summary['total_keep_s']}s[/green] / "
            f"[red]cut {summary['total_cut_s']}s[/red] → {edl_path}"
        )

        if summary["total_keep_s"] > cfg.output.max_duration_s:
            warnings.append(
                f"Output duration {summary['total_keep_s']}s exceeds max_duration_s={cfg.output.max_duration_s}s"
            )

        if dry_run:
            console.print("[yellow]--dry-run:[/yellow] skipping render.")
            return warnings

        # --- Caption rendering ---
        caption_words = _remap_kept_words(all_words, edl)

        srt_path = output_dir / f"{output_path.stem}.srt"
        from .caption import write_srt
        write_srt(caption_words, srt_path)
        console.print(f"  SRT → {srt_path}")

        caption_frames = []
        if cfg.captions.enabled and cfg.captions.style != "none":
            console.print("[bold]Step 6b/6[/bold] Rendering caption frames…")
            t = time.perf_counter()
            cap_dir = tmp / "captions"
            caption_frames = render_caption_frames(
                caption_words, cfg.captions, cap_dir,
                fps=cfg.output.fps,
                resolution=tuple(cfg.output.resolution),
            )
            _tlog(time.perf_counter() - t, f"{len(caption_frames)} frames")

        # --- Render ---
        from .renderer import _USE_VIDEOTOOLBOX
        encoder = "h264_videotoolbox (hardware)" if _USE_VIDEOTOOLBOX else "libx264 (software)"
        console.print(f"[bold]Step 6c/6[/bold] Rendering final video… encoder: [cyan]{encoder}[/cyan]")
        t = time.perf_counter()
        out = do_render(edl, caption_frames, cfg, output_path)
        console.print(f"\n[green bold]Done![/green bold] → {out}  ({time.perf_counter() - t:.1f}s)")

    return warnings


# ---------------------------------------------------------------------------
# reelcut transcribe
# ---------------------------------------------------------------------------

@app.command()
def transcribe(
    video: str = typer.Argument(..., help="Path to video file."),
    model: str = typer.Option("large-v2", help="Whisper model size."),
    language: str = typer.Option("en", help="Language code."),
    compute_type: str = typer.Option("int8", help="int8 | float16"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Transcribe a video file and print word-level timestamps."""
    from .audio import extract_audio
    from .config import WhisperConfig
    from .transcriber import transcribe as do_transcribe, align

    wcfg = WhisperConfig(model=model, compute_type=compute_type, language=language)  # type: ignore[arg-type]

    with tempfile.TemporaryDirectory() as tmpdir:
        wav = Path(tmpdir) / "audio.wav"
        console.print("Extracting audio…")
        extract_audio(video, wav)

        console.print("Transcribing…")
        words = do_transcribe(wav, wcfg)

        console.print("Aligning timestamps…")
        words = align(words, wav, wcfg)

    table = Table("#", "Word", "Start", "End", "Conf")
    for i, w in enumerate(words):
        table.add_row(str(i), w.word, f"{w.start:.3f}s", f"{w.end:.3f}s", f"{w.confidence:.2f}")
    console.print(table)
    console.print(f"\n{len(words)} words total.")


# ---------------------------------------------------------------------------
# reelcut preview-edl
# ---------------------------------------------------------------------------

@app.command(name="preview-edl")
def preview_edl(
    edl_path: str = typer.Argument(..., help="Path to .edl.json file."),
) -> None:
    """Print a summary of an EDL file in the terminal."""
    from .edl import load_edl, edl_summary

    try:
        edl = load_edl(edl_path)
    except FileNotFoundError as exc:
        err_console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1)

    summary = edl_summary(edl)

    console.print(f"\n[bold]EDL:[/bold] {edl_path}")
    console.print(f"  Keep segments : {summary['keep_segments']}")
    console.print(f"  Cut segments  : {summary['cut_segments']}")
    console.print(f"  Keep duration : [green]{summary['total_keep_s']}s[/green]")
    console.print(f"  Cut duration  : [red]{summary['total_cut_s']}s[/red]")
    console.print(f"  Cut reasons   : {summary['reasons']}")

    table = Table("#", "Clip", "Start", "End", "Duration", "Keep", "Reason")
    for i, entry in enumerate(edl):
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
# Helpers
# ---------------------------------------------------------------------------

def _remap_kept_words(words: list, edl: list) -> list:
    """Remap kept WordTimestamp objects from source clip time to output video time.

    Uses the EDL cut entries to compute per-word timestamp offsets rather than
    a timing-overlap check, so no word that was explicitly marked keep=True can
    fall through due to floating-point boundary conditions.

    For each clip, the output timeline starts at 0 (single clip) or at the end
    of the previous clip's kept duration (multi-clip). Within a clip, each cut
    interval shifts subsequent words earlier by the duration of that cut.
    """
    from .transcriber import WordTimestamp

    # Determine clip order from EDL (first appearance wins)
    clip_order: list[str] = []
    for entry in edl:
        if entry.source_clip not in clip_order:
            clip_order.append(entry.source_clip)

    # Per clip: total kept duration, start of first kept segment, cut intervals
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

    # Cumulative output offset where each clip's contribution begins
    clip_base: dict[str, float] = {}
    acc = 0.0
    for c in clip_order:
        clip_base[c] = acc
        acc += keep_dur.get(c, 0.0)

    remapped = []
    for w in words:
        if not w.keep:
            continue
        c = w.clip_path
        cuts = cut_intervals.get(c, [])
        first_start = first_keep_start.get(c, 0.0)
        # Only count cuts within the kept region (after first keep start).
        # Pre-keep cuts are already absorbed by subtracting first_start.
        cut_offset = sum(e - s for s, e in cuts if s >= first_start and e <= w.start)
        intra = w.start - first_start - cut_offset
        new_start = clip_base.get(c, 0.0) + intra
        new_end = new_start + (w.end - w.start)
        remapped.append(WordTimestamp(
            word=w.word,
            start=round(max(0.0, new_start), 4),
            end=round(max(0.0, new_end), 4),
            confidence=w.confidence,
            clip_path=c,
        ))

    return sorted(remapped, key=lambda w: w.start)


def _collect_clips(cfg) -> list[str]:
    """Return ordered list of source clip paths from config."""
    clips_folder = cfg.input.clips_folder
    if clips_folder:
        folder = Path(clips_folder)
        video_exts = {".mp4", ".mov", ".mkv"}
        clips = sorted(
            [p for p in folder.iterdir() if p.suffix.lower() in video_exts],
            key=lambda p: p.stat().st_mtime,
        )
        if not clips:
            raise typer.BadParameter(f"No video files found in clips_folder: {folder}")
        return [str(c) for c in clips]
    return [cfg.input.footage]


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