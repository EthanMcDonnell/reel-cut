"""Video renderer — FFmpeg render from EDL with optional caption overlay."""
from __future__ import annotations

import concurrent.futures
import subprocess
import sys
import tempfile
from pathlib import Path

import ffmpeg
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn

from .caption import CaptionFrame
from .config import ReelCutConfig
from .edl import EDLEntry, edl_summary


def _videotoolbox_available() -> bool:
    if sys.platform != "darwin":
        return False
    try:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            capture_output=True, text=True, timeout=5,
        )
        return "h264_videotoolbox" in result.stdout
    except Exception:
        return False


_USE_VIDEOTOOLBOX = _videotoolbox_available()


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

    n_workers = min(config.output.render_workers, len(keep_entries))

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TimeElapsedColumn(),
    ) as progress:
        task = progress.add_task("Rendering…", total=None)

        with tempfile.TemporaryDirectory() as tmpdir:
            # Step 1: extract and trim each keep segment to a temp clip
            segment_paths = _extract_segments(keep_entries, tmpdir, progress, task, n_workers, config.output.fps)

            # Step 2: concatenate segments (stream copy — no re-encode)
            progress.update(task, description="Concatenating segments…")
            concat_path = Path(tmpdir) / "concat.mkv"
            _concatenate(segment_paths, concat_path)

            # Step 3: final encode to output spec (caption overlay folded in if present)
            caption_seq: tuple[Path, int] | None = None
            if caption_frames:
                progress.update(task, description="Preparing captions…")
                caption_seq = _prepare_caption_sequence(caption_frames, config, tmpdir)

            progress.update(task, description="Encoding final output…")
            _final_encode(concat_path, output_path, config, caption_seq)

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
    n_workers: int,
    fps: int,
) -> list[Path]:
    """Trim each EDL keep entry to a temp file using frame-accurate trim + re-encode.

    Uses the trim/atrim filter approach instead of stream copy so cuts land on
    exact timestamps regardless of keyframe placement.

    Segments are extracted in parallel. Each FFmpeg job is independent, so N workers
    run simultaneously. Paths are pre-allocated by index so concatenation order is
    preserved regardless of completion order.
    """
    n = len(entries)
    # MKV + FLAC: lossless audio, no encoder delay. AAC delay accumulates across
    # independently-encoded segments on stream copy — converted to AAC once in _final_encode.
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
                # No fps filter here: applying per-segment VFR→CFR causes video and
                # audio durations to diverge slightly each segment (-shortest clips one),
                # and the error accumulates across all keep segments into audible A/V drift.
                # CFR conversion happens once in _final_encode on the full concat stream.
            )
            audio = (
                src.audio
                .filter("atrim", start=entry.start, end=entry.end)
                .filter("asetpts", "PTS-STARTPTS")
                # No apad: apad + separate filter chains deadlocks when audio waits
                # for video EOF signal that never arrives. -shortest handles any
                # minor audio/video length mismatch without hanging.
            )
            vcodec = "h264_videotoolbox" if _USE_VIDEOTOOLBOX else "libx264"
            encode_kwargs: dict = dict(
                vcodec=vcodec,
                acodec="flac",
                pix_fmt="yuv420p",
            )
            if not _USE_VIDEOTOOLBOX:
                encode_kwargs["preset"] = "ultrafast"
            else:
                encode_kwargs["b:v"] = "8000k"

            # ffmpeg-python converts shortest=True to "-shortest True" which FFmpeg
            # parses as a filename; compile the command and insert the flag manually.
            cmd = (
                ffmpeg
                .output(video, audio, str(out), **encode_kwargs)
                .overwrite_output()
                .compile()
            )
            cmd.insert(-1, "-shortest")
            proc = subprocess.run(cmd, capture_output=True, timeout=300)
            if proc.returncode != 0:
                raise ffmpeg.Error("ffmpeg", proc.stdout, proc.stderr)
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Segment {i} extraction timed out after 300s — FFmpeg may be hung")
        except ffmpeg.Error as exc:
            stderr = exc.stderr.decode() if exc.stderr else ""
            raise RuntimeError(f"Failed to extract segment {i} from {entry.source_clip}:\n{stderr}") from exc

    progress.update(task, description=f"Extracting {n} segments ({n_workers} parallel)…")
    with concurrent.futures.ThreadPoolExecutor(max_workers=n_workers) as executor:
        futures = {executor.submit(_extract_one, i): i for i in range(n)}
        completed = 0
        for future in concurrent.futures.as_completed(futures):
            future.result()
            completed += 1
            progress.update(task, description=f"Extracting segments… {completed}/{n}")

    return paths


def _concatenate(segment_paths: list[Path], output: Path) -> None:
    """Write a concat list file and join segments with FFmpeg concat demuxer."""
    concat_list = output.parent / "concat_list.txt"
    with concat_list.open("w") as f:
        for p in segment_paths:
            f.write(f"file '{p}'\n")

    try:
        (
            ffmpeg
            .input(str(concat_list), format="concat", safe=0)
            .output(str(output), vcodec="copy", acodec="copy")
            .overwrite_output()
            .run(quiet=True)
        )
    except ffmpeg.Error as exc:
        stderr = exc.stderr.decode() if exc.stderr else ""
        raise RuntimeError(f"FFmpeg concat failed:\n{stderr}") from exc


def _prepare_caption_sequence(
    caption_frames: list[CaptionFrame],
    config: ReelCutConfig,
    tmpdir: str,
) -> tuple[Path, int]:
    """Build the symlinked PNG sequence for caption overlay. Returns (seq_dir, min_frame)."""
    frame_map: dict[int, str] = {cf.frame_number: cf.image_path for cf in caption_frames}
    min_frame = min(frame_map)
    max_frame = max(frame_map)

    seq_dir = Path(tmpdir) / "cap_seq"
    seq_dir.mkdir(exist_ok=True)
    blank = _blank_frame(config.output.resolution[0], config.output.resolution[1], seq_dir)

    for fn in range(min_frame, max_frame + 1):
        dest = seq_dir / f"cap_{fn:06d}.png"
        src = frame_map.get(fn, str(blank))
        if dest.is_symlink() or dest.exists():
            dest.unlink()
        dest.symlink_to(src)

    return seq_dir, min_frame


def _final_encode(
    input_path: Path,
    output_path: Path,
    config: ReelCutConfig,
    caption_seq: tuple[Path, int] | None = None,
) -> None:
    """Re-encode to final output spec, optionally overlaying caption frames in the same pass."""
    w, h = config.output.resolution
    fps = config.output.fps

    def _build_streams() -> tuple:
        main = ffmpeg.input(str(input_path))
        # VFR → CFR once on the full concatenated stream. Doing this per-segment
        # (in _extract_segments) causes cumulative A/V drift when -shortest clips
        # differing video/audio durations at each segment boundary.
        video = main.video.filter("fps", fps=fps)
        # async resampling keeps audio locked to video PTS after the fps conversion.
        audio = main.audio.filter("aresample", **{"async": 1000})
        if caption_seq is not None:
            seq_dir, min_frame = caption_seq
            overlay_raw = ffmpeg.input(
                str(seq_dir / "cap_%06d.png"),
                framerate=fps,
                start_number=min_frame,
            )
            video = ffmpeg.overlay(
                video,
                overlay_raw.video.filter("format", "rgba"),
                eof_action="pass",
            )
        video = video.filter("scale", w, h, force_original_aspect_ratio="disable")
        return video, audio

    common: dict = dict(
        acodec="aac",
        audio_bitrate=config.output.audio_bitrate,
        r=fps,
        pix_fmt="yuv420p",
        movflags="+faststart",
    )

    if _USE_VIDEOTOOLBOX:
        video, audio = _build_streams()
        try:
            vt_kwargs = {**common, "vcodec": "h264_videotoolbox", "b:v": "8000k"}
            (
                ffmpeg
                .output(video, audio, str(output_path), **vt_kwargs)
                .overwrite_output()
                .run(quiet=True)
            )
            return
        except ffmpeg.Error:
            pass  # fall through to libx264

    video, audio = _build_streams()
    try:
        (
            ffmpeg
            .output(video, audio, str(output_path), vcodec="libx264", **common)
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
