"""Video renderer — FFmpeg render from EDL with caption overlay."""
from __future__ import annotations

import concurrent.futures
import tempfile
from pathlib import Path

import ffmpeg
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn

from .caption import CaptionFrame
from .config import ReelCutConfig
from .edl import EDLEntry, edl_summary


def render(
    edl: list[EDLEntry],
    caption_frames: list[CaptionFrame],
    config: ReelCutConfig,
    output_path: str | Path | None = None,
) -> Path:
    """Render final video from EDL keep-segments with optional caption overlay.

    - Reads only `keep=True` EDL entries.
    - Concatenates segments via FFmpeg.
    - Burns in caption PNG overlay frames.
    - Warns if output exceeds max_duration_s.
    - Returns path to the output MP4.
    """
    output_path = Path(output_path) if output_path else Path(config.output.location) / "output.mp4"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    keep_entries = [e for e in edl if e.keep]
    if not keep_entries:
        raise ValueError("EDL has no keep segments — nothing to render.")

    summary = edl_summary(edl)
    total_keep_s = summary["total_keep_s"]

    if total_keep_s > config.output.max_duration_s:
        from rich.console import Console
        Console().print(
            f"[yellow]Warning:[/yellow] output duration {total_keep_s:.1f}s exceeds "
            f"max_duration_s={config.output.max_duration_s}s — rendering anyway."
        )

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TimeElapsedColumn(),
    ) as progress:
        task = progress.add_task("Rendering…", total=None)

        with tempfile.TemporaryDirectory() as tmpdir:
            # Step 1: extract and trim each keep segment to a temp clip
            segment_paths = _extract_segments(keep_entries, tmpdir, progress, task)

            # Step 2: concatenate segments
            progress.update(task, description="Concatenating segments…")
            # MKV container matches intermediate segments (H.264 + FLAC, stream copy)
            concat_path = Path(tmpdir) / "concat.mkv"
            _concatenate(segment_paths, concat_path, config)

            # Step 3: burn in captions (if any)
            if caption_frames:
                progress.update(task, description="Burning in captions…")
                captioned_path = Path(tmpdir) / "captioned.mkv"
                _burn_captions(concat_path, caption_frames, captioned_path, config)
                final_input = captioned_path
            else:
                final_input = concat_path

            # Step 4: final encode to output spec
            progress.update(task, description="Encoding final output…")
            _final_encode(final_input, output_path, config)

        progress.update(task, description=f"Done → {output_path}", completed=1, total=1)

    return output_path


# ---------------------------------------------------------------------------
# Internal steps
# ---------------------------------------------------------------------------

def _extract_segments(
    entries: list[EDLEntry],
    tmpdir: str,
    progress,
    task,
) -> list[Path]:
    """Trim each EDL keep entry to a temp file using frame-accurate trim + re-encode.

    Uses the trim/atrim filter approach instead of stream copy so cuts land on
    exact timestamps regardless of keyframe placement.

    Segments are extracted in parallel (unsilence-style thread pool). Each FFmpeg
    job is independent, so N workers run simultaneously. Paths are pre-allocated
    by index so concatenation order is preserved regardless of completion order.
    """
    n = len(entries)
    # Use MKV + FLAC (lossless, no encoder delay) for intermediate segments.
    # AAC encoder delay (~1024 samples) accumulates across independently-encoded
    # segments when concatenated with stream copy, causing audio dropouts.
    # _final_encode converts to AAC once at the end.
    paths: list[Path] = [Path(tmpdir) / f"seg_{i:04d}.mkv" for i in range(n)]

    def _extract_one(i: int) -> None:
        entry = entries[i]
        out = paths[i]
        try:
            src = ffmpeg.input(entry.source_clip)
            video = (
                src.video
                .trim(start=entry.start, end=entry.end)
                .setpts("PTS-STARTPTS")
            )
            audio = (
                src.audio
                .filter("atrim", start=entry.start, end=entry.end)
                .filter("asetpts", "PTS-STARTPTS")
            )
            (
                ffmpeg
                .output(
                    video,
                    audio,
                    str(out),
                    vcodec="libx264",
                    acodec="flac",
                    pix_fmt="yuv420p",
                )
                .overwrite_output()
                .run(quiet=True)
            )
        except ffmpeg.Error as exc:
            stderr = exc.stderr.decode() if exc.stderr else ""
            raise RuntimeError(f"Failed to extract segment {i} from {entry.source_clip}:\n{stderr}") from exc

    n_workers = min(4, n)
    progress.update(task, description=f"Extracting {n} segments ({n_workers} parallel)…")
    with concurrent.futures.ThreadPoolExecutor(max_workers=n_workers) as executor:
        futures = {executor.submit(_extract_one, i): i for i in range(n)}
        completed = 0
        for future in concurrent.futures.as_completed(futures):
            future.result()  # re-raises any extraction error immediately
            completed += 1
            progress.update(task, description=f"Extracting segments… {completed}/{n}")

    return paths


def _concatenate(segment_paths: list[Path], output: Path, config: ReelCutConfig) -> None:
    """Write a concat list file and join segments with FFmpeg concat demuxer."""
    concat_list = output.parent / "concat_list.txt"
    with concat_list.open("w") as f:
        for p in segment_paths:
            f.write(f"file '{p}'\n")

    try:
        (
            ffmpeg
            .input(str(concat_list), format="concat", safe=0)
            .output(
                str(output),
                vcodec="copy",
                acodec="copy",
            )
            .overwrite_output()
            .run(quiet=True)
        )
    except ffmpeg.Error as exc:
        stderr = exc.stderr.decode() if exc.stderr else ""
        raise RuntimeError(f"FFmpeg concat failed:\n{stderr}") from exc


def _burn_captions(
    input_path: Path,
    caption_frames: list[CaptionFrame],
    output_path: Path,
    config: ReelCutConfig,
) -> None:
    """Overlay PNG caption frames onto the video using FFmpeg overlay filter."""
    # Build a frame-accurate overlay using a concat of caption images
    # Strategy: create a video stream from caption PNGs at the same fps,
    # then overlay it with blend mode (captions have transparency).
    fps = config.output.fps
    caption_dir = Path(caption_frames[0].image_path).parent

    # Write a PNG list for the caption image sequence
    frame_map: dict[int, str] = {cf.frame_number: cf.image_path for cf in caption_frames}
    if not frame_map:
        return
    min_frame = min(frame_map)
    max_frame = max(frame_map)

    # Create a padded sequence directory where missing frames are blank
    seq_dir = caption_dir / "seq"
    seq_dir.mkdir(exist_ok=True)
    blank = _blank_frame(config.output.resolution[0], config.output.resolution[1], seq_dir)

    for fn in range(min_frame, max_frame + 1):
        dest = seq_dir / f"cap_{fn:06d}.png"
        src = frame_map.get(fn, str(blank))
        if dest.is_symlink() or dest.exists():
            dest.unlink()
        dest.symlink_to(src)

    try:
        main = ffmpeg.input(str(input_path))
        overlay_raw = ffmpeg.input(
            str(seq_dir / "cap_%06d.png"),
            framerate=fps,
            start_number=min_frame,
        )
        # Convert overlay PNGs to rgba so transparency is respected
        overlay_rgba = overlay_raw.video.filter("format", "rgba")
        (
            ffmpeg
            .overlay(main.video, overlay_rgba, eof_action="pass")
            .output(
                main.audio,
                str(output_path),
                vcodec="libx264",
                acodec="copy",
                r=fps,
                pix_fmt="yuv420p",
            )
            .overwrite_output()
            .run(quiet=True)
        )
    except ffmpeg.Error as exc:
        stderr = exc.stderr.decode() if exc.stderr else ""
        raise RuntimeError(f"Caption burn-in failed:\n{stderr}") from exc


def _final_encode(input_path: Path, output_path: Path, config: ReelCutConfig) -> None:
    """Re-encode to final output spec: 1080x1920 H.264, AAC, target fps."""
    w, h = config.output.resolution
    fps = config.output.fps

    try:
        (
            ffmpeg
            .input(str(input_path))
            .output(
                str(output_path),
                vcodec="libx264",
                acodec="aac",
                audio_bitrate=config.output.audio_bitrate,
                r=fps,
                vf=f"scale={w}:{h}:force_original_aspect_ratio=disable",
                pix_fmt="yuv420p",
                movflags="+faststart",
            )
            .overwrite_output()
            .run(quiet=True)
        )
    except ffmpeg.Error as exc:
        stderr = exc.stderr.decode() if exc.stderr else ""
        raise RuntimeError(f"Final encode failed:\n{stderr}") from exc


def _blank_frame(w: int, h: int, directory: Path) -> Path:
    """Create and cache a fully transparent PNG blank frame."""
    from PIL import Image
    path = directory / "_blank.png"
    if not path.exists():
        Image.new("RGBA", (w, h), (0, 0, 0, 0)).save(str(path))
    return path
