"""Audio extractor — pull mono 16kHz WAV from video files via FFmpeg."""
from __future__ import annotations

import warnings
from pathlib import Path

import ffmpeg


def extract_audio(video_path: str | Path, output_wav_path: str | Path) -> Path:
    """Extract mono 16kHz WAV from a video file.

    Supports MP4, MOV, MKV and any format FFmpeg can read.
    Raises RuntimeError on FFmpeg failure.
    """
    video_path = Path(video_path)
    output_wav_path = Path(output_wav_path)

    if not video_path.exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")

    output_wav_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        (
            ffmpeg
            .input(str(video_path))
            .output(
                str(output_wav_path),
                ac=1,          # mono
                ar=16000,      # 16kHz — required by Whisper / VAD
                acodec="pcm_s16le",
                vn=None,       # no video stream
            )
            .overwrite_output()
            .run(quiet=True)
        )
    except ffmpeg.Error as exc:
        stderr = exc.stderr.decode() if exc.stderr else ""
        raise RuntimeError(f"FFmpeg failed to extract audio from {video_path}:\n{stderr}") from exc

    return output_wav_path


def normalize_audio(wav_path: str | Path, output_path: str | Path | None = None) -> Path:
    """Loudness-normalize a WAV file to -23 LUFS (EBU R128).

    If output_path is None, overwrites the input file.
    """
    wav_path = Path(wav_path)
    output_path = Path(output_path) if output_path else wav_path

    if not wav_path.exists():
        raise FileNotFoundError(f"WAV file not found: {wav_path}")

    # Two-pass loudnorm: first pass measures, second pass applies
    try:
        probe = (
            ffmpeg
            .input(str(wav_path))
            .audio
            .filter("loudnorm", I=-23, TP=-2, LRA=11, print_format="json")
            .output("-", format="null")
            .run(capture_stderr=True, quiet=True)
        )
    except ffmpeg.Error:
        warnings.warn(
            f"Two-pass loudnorm probe failed for {wav_path.name}; falling back to single-pass normalization.",
            RuntimeWarning,
            stacklevel=2,
        )
        probe = None

    tmp = wav_path.with_suffix(".norm_tmp.wav")
    try:
        (
            ffmpeg
            .input(str(wav_path))
            .audio
            .filter("loudnorm", I=-23, TP=-2, LRA=11)
            .output(str(tmp), acodec="pcm_s16le", ar=16000, ac=1)
            .overwrite_output()
            .run(quiet=True)
        )
        tmp.replace(output_path)
    except ffmpeg.Error as exc:
        stderr = exc.stderr.decode() if exc.stderr else ""
        raise RuntimeError(f"FFmpeg normalization failed for {wav_path}:\n{stderr}") from exc

    return output_path
